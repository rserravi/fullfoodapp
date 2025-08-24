from __future__ import annotations
from typing import List, Dict, Tuple, Optional
import json
import math
import hashlib

from sqlmodel import Session

from ..schemas import RecipeNeutral, IngredientItem, AggregatedItem
from ..config import settings
from ..llm import generate_json
from ..utils.json_repair import repair_json_minimal, repair_via_llm
from .cache import make_key, get_payload, set_payload

# --- Normalización de unidades ---
UNIT_ALIASES = {
    "g": ("g", 1.0), "gr": ("g", 1.0), "gramo": ("g", 1.0), "gramos": ("g", 1.0),
    "kg": ("g", 1000.0), "kilo": ("g", 1000.0), "kilogramo": ("g", 1000.0), "kilogramos": ("g", 1000.0),

    "ml": ("ml", 1.0), "mililitro": ("ml", 1.0), "mililitros": ("ml", 1.0),
    "l": ("ml", 1000.0), "lt": ("ml", 1000.0), "litro": ("ml", 1000.0), "litros": ("ml", 1000.0),
    "cc": ("ml", 1.0), "cl": ("ml", 10.0),

    "ud": ("ud", 1.0), "unidad": ("ud", 1.0), "unidades": ("ud", 1.0), "pieza": ("ud", 1.0), "piezas": ("ud", 1.0),
}

VOLUME_SPOONS = {
    "cda": 15.0, "cucharada": 15.0, "cucharadas": 15.0,
    "cdta": 5.0, "cucharadita": 5.0, "cucharaditas": 5.0,
    "taza": 240.0, "tazas": 240.0, "cup": 240.0, "cups": 240.0,
}

LIQUID_HINTS = {"agua", "aceite", "leche", "caldo", "vinagre", "zumo", "salsa"}

def _norm_name(name: str) -> str:
    return " ".join(name.strip().lower().split())

def _sha1_json(obj) -> str:
    blob = json.dumps(obj, sort_keys=True, ensure_ascii=False)
    return hashlib.sha1(blob.encode("utf-8")).hexdigest()

def canonical_unit(unit: Optional[str]) -> Tuple[Optional[str], Optional[float]]:
    if not unit:
        return None, None
    u = unit.strip().lower()
    if u in UNIT_ALIASES:
        canon, factor = UNIT_ALIASES[u]
        return canon, factor
    if u in VOLUME_SPOONS:
        return "ml", VOLUME_SPOONS[u]
    return None, None

def normalize_item(it: IngredientItem) -> IngredientItem:
    name = _norm_name(it.name)
    qty = it.qty
    unit = it.unit.lower() if it.unit else None

    if unit in VOLUME_SPOONS:
        unit = "ml"
        qty = (qty or 0) * VOLUME_SPOONS[unit] if qty is not None else None

    canon, factor = canonical_unit(unit)
    if canon:
        unit = canon
        if qty is not None and factor and factor != 1.0:
            qty = qty * factor

    if (qty is None or qty == 0) and (not unit) and any(tok in name for tok in LIQUID_HINTS):
        unit = "ml"

    return IngredientItem(name=name, qty=qty, unit=unit)

def aggregate_items(items: List[IngredientItem]) -> List[AggregatedItem]:
    acc: Dict[Tuple[str, str], float] = {}
    for raw in items:
        it = normalize_item(raw)
        if it.qty is None or it.unit is None:
            key = (it.name, "ud")
            acc[key] = acc.get(key, 0.0) + 1.0
            continue
        key = (it.name, it.unit)
        acc[key] = acc.get(key, 0.0) + float(it.qty)

    out: List[AggregatedItem] = []
    for (name, unit), qty in sorted(acc.items()):
        q = float(qty)
        if unit in ("g", "ml", "ud"):
            if abs(q - round(q)) < 1e-6:
                q = float(int(round(q)))
        out.append(AggregatedItem(name=name, qty=q, unit=unit))
    return out

# ---------------------- Extracción LLM con CACHE ----------------------

async def llm_extract_ingredients(recipe: RecipeNeutral, session: Session, user_id: str) -> List[IngredientItem]:
    """
    Usa cache por (user_id, hash_receta) durante 7 días.
    """
    from pathlib import Path

    recipe_dump = recipe.model_dump()
    rec_hash = _sha1_json(recipe_dump)
    cache_key = make_key("extract", {"recipe": rec_hash})

    cached = get_payload(session, user_id, cache_key)
    if cached is not None:
        try:
            return [IngredientItem(**obj) for obj in cached]
        except Exception:
            pass  # si hay algo raro en cache, seguimos y recalculamos

    # --- LLM call ---
    tmpl_path = Path(__file__).resolve().parents[1] / "prompts" / "ingredient_extraction.md"
    tmpl = tmpl_path.read_text(encoding="utf-8")
    prompt = (tmpl
              .replace("{{portions}}", str(recipe.portions))
              .replace("{{recipe_json}}", json.dumps(recipe_dump, ensure_ascii=False, indent=2)))

    try:
        raw = await generate_json(prompt, model=settings.llm_model, temperature=0.0, max_tokens=800)
    except Exception:
        names = _fallback_names(recipe)
        items = [IngredientItem(name=n, qty=None, unit=None) for n in names]
        # guardamos fallback también para no recalcular cada vez (TTL corto)
        set_payload(session, user_id, cache_key, [i.model_dump() for i in items], ttl_seconds=24*3600)
        return items

    # Parse
    try:
        data = json.loads(raw)
    except Exception:
        ok, repaired = repair_json_minimal(raw)
        if ok:
            data = json.loads(repaired)
        else:
            fixed = await repair_via_llm(raw)
            data = json.loads(fixed)

    if isinstance(data, dict) and "items" in data and isinstance(data["items"], list):
        data = data["items"]

    items: List[IngredientItem] = []
    if isinstance(data, list):
        for obj in data:
            if not isinstance(obj, dict) or "name" not in obj:
                continue
            name = str(obj.get("name", "")).strip()
            if not name:
                continue
            qty = obj.get("qty", None)
            try:
                qty = float(qty) if qty is not None else None
            except Exception:
                qty = None
            unit = obj.get("unit", None)
            unit = str(unit).strip().lower() if unit is not None else None
            if unit not in (None, "g", "ml", "ud", "kg", "l",
                            "gramos", "gramo", "litros", "litro",
                            "taza", "tazas", "cda", "cucharada", "cucharadas",
                            "cdta", "cucharadita", "cucharaditas"):
                unit = None
            items.append(IngredientItem(name=name, qty=qty, unit=unit))

    if not items:
        names = _fallback_names(recipe)
        items = [IngredientItem(name=n, qty=None, unit=None) for n in names]

    # Cache 7 días
    set_payload(session, user_id, cache_key, [i.model_dump() for i in items], ttl_seconds=7*24*3600)
    return items

def _fallback_names(recipe: RecipeNeutral) -> List[str]:
    seen = set()
    out: List[str] = []
    for step in recipe.steps_generic:
        for ing in step.ingredients or []:
            n = _norm_name(ing)
            if n and n not in seen:
                seen.add(n)
                out.append(n)
    return out

async def extract_and_aggregate(recipe: RecipeNeutral, session: Session, user_id: str) -> List[AggregatedItem]:
    items = await llm_extract_ingredients(recipe, session, user_id)
    return aggregate_items(items)
