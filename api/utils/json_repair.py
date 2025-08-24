import json
import re
from typing import Tuple

FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", flags=re.IGNORECASE | re.MULTILINE)

def _strip_fences(s: str) -> str:
    return FENCE_RE.sub("", s).strip()

def _trim_to_braces(s: str) -> str:
    """Intenta recortar al primer '{' y último '}' equilibrados."""
    first = s.find("{")
    last = s.rfind("}")
    if first != -1 and last != -1 and last > first:
        return s[first:last+1]
    return s

def _remove_trailing_commas(s: str) -> str:
    s = re.sub(r",\s*([}\]])", r"\1", s)
    return s

def repair_json_minimal(text: str) -> Tuple[bool, str]:
    """
    Intenta reparar JSON común:
    - eliminar fences/backticks
    - recortar a llaves exteriores
    - quitar comas finales
    Devuelve (ok, json_str_posible)
    """
    candidate = _strip_fences(text)
    candidate = _trim_to_braces(candidate)
    candidate = _remove_trailing_commas(candidate)
    try:
        json.loads(candidate)
        return True, candidate
    except Exception:
        pass
    # último intento: reemplazar comillas simples si no rompen números
    candidate2 = re.sub(r"(?<!\\)'", '"', candidate)
    try:
        json.loads(candidate2)
        return True, candidate2
    except Exception:
        return False, candidate

async def repair_via_llm(text: str) -> str:
    """
    Pide al LLM que devuelva JSON válido que represente el mismo objeto.
    Usa format=json para forzar salida parseable.
    """
    from ..llm import generate_json  # import tardío para evitar ciclos
    prompt = (
        "Eres un reparador de JSON. Devuelve exclusivamente JSON válido, sin comentarios, "
        "que represente el mismo contenido. Si faltan campos, déjalos con valores razonables.\n\n"
        "Contenido a reparar:\n"
        f"{text}\n"
    )
    return await generate_json(prompt, temperature=0.0)
