from __future__ import annotations

from typing import List, Dict, Any, Optional, Tuple
import json
import re
from collections import defaultdict

from sqlmodel import Session

from ..schemas import AggregatedItem, RecipeNeutral
from .ingredients import extract_ingredients  # parser básico de ingredientes desde RecipeNeutral
from .catalog import categorize_names

# Opcional: si existe la util de LLM del generador, la usamos; si no, seguimos con fallback sin romper.
try:
    from ..routes.generate import _call_llm as call_llm  # type: ignore
except Exception:  # pragma: no cover
    call_llm = None  # type: ignore


# -----------------------------
# Helpers de parsing/normalización
# -----------------------------

_JSON_BLOCK_RE = re.compile(
    r"(?P<json>(\[\s*(\{.*?\}\s*,?\s*)+\])|(\{\s*.*?\s*\}))",
    re.DOTALL,
)

def _safe_json_parse(text: str) -> Optional[Any]:
    """
    Intenta parsear JSON de forma robusta:
    - Recorta fences ```...```
    - Busca primer bloque JSON con regex (array u objeto)
    - Devuelve None si no hay JSON válido
    """
    if not text or not isinstance(text, str):
        return None

    t = text.strip()

    # Quita bloques de markdown si vienen
    if t.startswith("```"):
        # elimina la primera y última fence si existen
        t = re.sub(r"^```[a-zA-Z0-9_-]*", "", t).strip()
        t = re.sub(r"```$", "", t).strip()

    # ¿es JSON completo ya?
    try:
        return json.loads(t)
    except Exception:
        pass

    # Busca el primer bloque con pinta de JSON
    m = _JSON_BLOCK_RE.search(t)
    if not m:
        return None

    block = m.group("json")
    try:
        return json.loads(block)
    except Exception:
        return None


def _norm_name(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().lower())


def _try_qty_unit(s: str) -> Tuple[Optional[float], Optional[str]]:
    """
    Heurística muy simple para detectar algo tipo "200 g", "2 ud", "1 lata".
    Si no detecta, devuelve (None, None).
    """
    if not s:
        return None, None
    m = re.match(r"^\s*(\d+(?:[.,]\d+)?)\s*([a-zA-ZñÑáéíóúÁÉÍÓÚ/]+)\s*$", s)
    if not m:
        return None, None
    qty_raw = m.group(1).replace(",", ".")
    try:
        qty = float(qty_raw)
    except Exception:
        qty = None
    unit = m.group(2).lower()
    return qty, unit


# -----------------------------
# LLM extraction (opcional, tolerante a fallos)
# -----------------------------

async def llm_extract_ingredients(
    recipe: RecipeNeutral,
    session: Session,
    user_id: str,
) -> List[Dict[str, Any]]:
    """
    Intenta pedir al LLM una estructura JSON con ingredientes.
    Formato esperado por item: {"name": str, "qty": float|int|null, "unit": str|null}
    Nunca levanta excepción: si algo va mal, devuelve [].
    """
    if call_llm is None:
        return []

    # Prompt minimalista y robusto (evita depender de archivo de plantilla).
    # Si quieres moverlo a /api/prompts/ más adelante, sin problema.
    sys_prompt = (
        "Eres un asistente que EXTRAe ingredientes a partir de una receta en JSON.\n"
        "Responde EXCLUSIVAMENTE con un array JSON de objetos con claves: name, qty, unit.\n"
        "Ejemplo: [{\"name\":\"aceite de oliva\",\"qty\":15,\"unit\":\"ml\"}, {\"name\":\"sal\",\"qty\":null,\"unit\":null}]"
    )
    user_payload = {
        "title": recipe.title,
        "portions": recipe.portions,
        "steps": recipe.steps_generic,
    }
    prompt = f"{sys_prompt}\n\nRECIPE_JSON:\n```json\n{json.dumps(user_payload, ensure_ascii=False)}\n```"

    try:
        raw = await call_llm(prompt)
    except Exception:
        return []

    data = _safe_json_parse(raw)
    if not isinstance(data, list):
        return []

    items: List[Dict[str, Any]] = []
    for it in data:
        if not isinstance(it, dict):
            continue
        name = _norm_name(str(it.get("name") or ""))
        if not name:
            continue
        qty = it.get("qty", None)
        unit = it.get("unit", None)
        # normaliza qty si viene como str "200 g"
        if isinstance(qty, str) and not unit:
            q, u = _try_qty_unit(qty)
            qty, unit = q, u
        # valida tipos
        if isinstance(qty, (int, float)):
            qv: Optional[float] = float(qty)
        else:
            qv = None
        uv: Optional[str] = (str(unit).lower() if isinstance(unit, str) and unit.strip() else None)
        items.append({"name": name, "qty": qv, "unit": uv})

    return items


# -----------------------------
# Agregado + categorización
# -----------------------------

def _aggregate_items(items: List[Dict[str, Any]]) -> List[AggregatedItem]:
    merged: Dict[Tuple[str, Optional[str]], float] = defaultdict(float)
    seen_keys: set = set()

    # Sumamos cantidades por (name, unit). Si qty es None, mantenemos una sola entrada.
    for it in items:
        name = _norm_name(it.get("name", ""))
        if not name:
            continue
        unit = it.get("unit", None)
        qty = it.get("qty", None)

        key = (name, unit if isinstance(unit, str) else None)
        if qty is None:
            # Si no hay cantidad, aseguramos que exista la clave (sin sumar)
            if key not in seen_keys and key not in merged:
                merged[key] = 0.0
                seen_keys.add(key)
            continue

        try:
            merged[key] += float(qty)
        except Exception:
            # si qty no es convertible, la ignoramos como None
            if key not in seen_keys and key not in merged:
                merged[key] = 0.0
                seen_keys.add(key)

    # Construimos lista resultante (qty 0.0 -> None para “desconocida”)
    result: List[AggregatedItem] = []
    for (name, unit), total in merged.items():
        q: Optional[float] = None if total == 0.0 else total
        result.append(AggregatedItem(name=name, qty=q, unit=unit, category=None))
    return result


async def extract_and_aggregate(
    recipe: RecipeNeutral,
    session: Session,
    user_id: str,
) -> List[AggregatedItem]:
    """
    Pipeline tolerante:
    1) Intenta LLM → lista [{name, qty, unit}]
    2) Si falla o viene vacío → fallback determinista a partir de los steps de la receta
    3) Agrega por (name,unit) y categoriza
    """
    items: List[Dict[str, Any]] = []

    # 1) LLM (no rompe si falla)
    try:
        items = await llm_extract_ingredients(recipe, session, user_id)
    except Exception:
        items = []

    # 2) Fallback determinista si hace falta
    if not items:
        names = extract_ingredients(recipe)  # List[str]
        items = [{"name": _norm_name(n), "qty": None, "unit": None} for n in names if _norm_name(n)]

    # 3) Agregado
    aggregated = _aggregate_items(items)

    # 4) Categorías
    cat_map = categorize_names(session, user_id, [a.name for a in aggregated])
    for a in aggregated:
        a.category = cat_map.get(a.name, None)

    # Orden amigable por categoría y nombre
    aggregated.sort(key=lambda x: ((x.category or "zzzz"), x.name))

    return aggregated
