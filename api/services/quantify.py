from __future__ import annotations
from typing import List, Dict, Tuple, Optional
import json
import math

from ..schemas import RecipeNeutral, IngredientItem, AggregatedItem
from ..config import settings
from ..llm import generate_json
from ..utils.json_repair import repair_json_minimal, repair_via_llm

# --- Normalización de unidades ---
# familias: masa(g), volumen(ml), unidades(ud)
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

# pistas muy simples de "líquido"
LIQUID_HINTS = {"agua", "aceite", "leche", "caldo", "vinagre", "zumo", "salsa"}

def _norm_name(name: str) -> str:
    return " ".join(name.strip().lower().split())

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

    # convertir "cucharadas"/"tazas" a ml
    if unit in VOLUME_SPOONS:
        unit = "ml"
        qty = (qty or 0) * VOLUME_SPOONS[unit] if qty is not None else None

    # alias de unidad
    canon, factor = canonical_unit(unit)
    if canon:
        unit = canon
        if qty is not None and factor and factor != 1.0:
            qty = qty * factor

    # pistas de líquidos: si no hay unidad ni qty, intentamos unit="ml" y qty=None
    if (qty is None or qty == 0) and (not unit) and any(tok in name for tok in LIQUID_HINTS):
        unit = "ml"

    # si no hay nada, dejamos qty/unit como None; agregador hará conteo por 'ud' si procede
    return IngredientItem(name=name, qty=qty, unit=unit)

def aggregate_items(items: List[IngredientItem]) -> List[AggregatedItem]:
    """
    Suma por (name, unit_familia) en canónicos:
      - masa: g
      - volumen: ml
      - unidades: ud
    Para elementos sin qty/unit → se contarán como 1 'ud' por ocurrencia.
    """
    acc: Dict[Tuple[str, str], float] = {}
    unknown: Dict[str, int] = {}

    for raw in items:
        it = normalize_item(raw)
        if it.qty is None or it.unit is None:
            # contamos ocurrencias como 1 ud
            key = (it.name, "ud")
            acc[key] = acc.get(key, 0.0) + 1.0
            continue
        key = (it.name, it.unit)
        acc[key] = acc.get(key, 0.0) + float(it.qty)

    out: List[AggregatedItem] = []
    for (name, unit), qty in sorted(acc.items()):
        # Redondeo “bonito”: g/ml sin decimales si > 1, ud sin decimales.
        if unit in ("g", "ml", "ud"):
            q = float(qty)
            if unit in ("g", "ml", "ud"):
                if abs(q - round(q)) < 1e-6:
                    q = float(int(round(q)))
            out.append(AggregatedItem(name=name, qty=q, unit=unit))
        else:
            out.append(AggregatedItem(name=name, qty=qty, unit=unit))
    return out

# ---------------------- Extracción LLM ----------------------

async def llm_extract_ingredients(recipe: RecipeNeutral) -> List[IngredientItem]:
    """
    Llama al LLM con un prompt estructurado y devuelve lista de IngredientItem.
    Fallback: si falla, devuelve nombres únicos sin qty ni unit.
    """
    from pathlib import Path

    tmpl_path = Path(__file__).resolve().parents[1] / "prompts" / "ingredient_extraction.md"
    tmpl = tmpl_path.read_text(encoding="utf-8")

    recipe_json = json.dumps(recipe.model_dump(), ensure_ascii=False, indent=2)
    prompt = (tmpl
              .replace("{{portions}}", str(recipe.portions))
              .replace("{{recipe_json}}", recipe_json))

    try:
        raw = await generate_json(prompt, model=settings.llm_model, temperature=0.0, max_tokens=800)
    except Exception:
        # fallo en llamada LLM → fallback nombres
        names = _fallback_names(recipe)
        return [IngredientItem(name=n, qty=None, unit=None) for n in names]

    # Parse estrictamente como lista
    data = None
    try:
        data = json.loads(raw)
    except Exception:
        ok, repaired = repair_json_minimal(raw)
        if ok:
            data = json.loads(repaired)
        else:
            fixed = await repair_via_llm(raw)
            data = json.loads(fixed)

    if not isinstance(data, list):
        # A veces devuelve {"items":[...]} → afinar
        if isinstance(data, dict) and "items" in data and isinstance(data["items"], list):
            data = data["items"]
        else:
            names = _fallback_names(recipe)
            return [IngredientItem(name=n, qty=None, unit=None) for n in names]

    items: List[IngredientItem] = []
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
        # limitar al vocabulario permitido
        if unit not in (None, "g", "ml", "ud", "kg", "l", "gramos", "gramo", "litros", "litro",
                        "taza", "tazas", "cda", "cucharada", "cucharadas", "cdta", "cucharadita", "cucharaditas"):
            unit = None
        items.append(IngredientItem(name=name, qty=qty, unit=unit))

    if not items:
        names = _fallback_names(recipe)
        items = [IngredientItem(name=n, qty=None, unit=None) for n in names]

    return items

def _fallback_names(recipe: RecipeNeutral) -> List[str]:
    # Extrae nombres tal cual de los steps; desduplica preservando orden
    seen = set()
    out: List[str] = []
    for step in recipe.steps_generic:
        for ing in step.ingredients or []:
            n = _norm_name(ing)
            if n and n not in seen:
                seen.add(n)
                out.append(n)
    return out

async def extract_and_aggregate(recipe: RecipeNeutral) -> List[AggregatedItem]:
    items = await llm_extract_ingredients(recipe)
    return aggregate_items(items)
