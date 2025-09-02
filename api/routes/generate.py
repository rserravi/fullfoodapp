from __future__ import annotations
from typing import List, Literal, Dict, Any
from pydantic import BaseModel, Field
from fastapi import APIRouter, Body, HTTPException, Depends
from pathlib import Path
import json, re

from ..config import settings
from ..schemas import RecipeNeutral
from ..embeddings import embed_dual
from ..vectorstore import search
from ..security import get_current_user
from ..llm import generate_json

router = APIRouter(tags=["recipes"], prefix="/recipes")

# -------------------------
# Modelos de petición / respuesta
# -------------------------
class RecipeGenRequest(BaseModel):
    ingredients: List[str] = Field(..., description="Lista de ingredientes principales")
    portions: int = Field(2, ge=1, le=12, description="Raciones deseadas")
    appliances: List[str] = Field(default_factory=list, description="Electrodomésticos del usuario (p.ej. ['sartén','microondas','airfryer'])")
    dietary: List[str] = Field(default_factory=list, description="Restricciones o preferencias (p.ej. ['vegetariano','sin gluten'])")
    top_k: int = Field(5, ge=1, le=8, description="Número de pasajes a recuperar del RAG")
    mode: Literal["strict", "hybrid", "creative"] = Field("hybrid", description="Modo de generación")

class SourceHit(BaseModel):
    id: str
    score: float
    title: str | None = None
    path: str | None = None
    chunk: int | None = None
    snippet: str | None = None

class RecipeGenResponse(BaseModel):
    recipe: RecipeNeutral
    mode: Literal["strict", "hybrid", "creative"]
    sources: List[SourceHit]

# -------------------------
# Resolución de carpeta de prompts
# -------------------------
REPO_ROOT = Path(__file__).resolve().parents[2]

def _resolve_prompts_dir() -> Path:
    tried: List[Path] = []
    # 1) Si viene por settings (PROMPTS_DIR), respétalo
    env_dir = getattr(settings, "prompts_dir", None)
    if env_dir:
        p = Path(env_dir)
        if not p.is_absolute():
            p = (REPO_ROOT / p).resolve()
        tried.append(p)
        if p.exists():
            return p
    # 2) Default preferido: api/prompts
    p_api = (REPO_ROOT / "api" / "prompts").resolve()
    tried.append(p_api)
    if p_api.exists():
        return p_api
    # 3) Alternativa: prompts en raíz
    p_root = (REPO_ROOT / "prompts").resolve()
    tried.append(p_root)
    if p_root.exists():
        return p_root
    # Si nada existe, devolvemos error claro
    raise FileNotFoundError(
        "No se encuentra la carpeta de prompts. Rutas intentadas:\n" +
        "\n".join(f"- {str(t)}" for t in tried)
    )

PROMPTS_DIR = _resolve_prompts_dir()

_TEMPLATE_MAP = {
    "strict":   "recipes.generate.strict.txt",
    "hybrid":   "recipes.generate.hybrid.txt",
    "creative": "recipes.generate.creative.txt",
}

def _read_template(mode: str) -> str:
    fname = _TEMPLATE_MAP.get(mode)
    if not fname:
        raise FileNotFoundError(f"Modo no soportado: {mode}")
    path = PROMPTS_DIR / fname
    if not path.exists():
        raise FileNotFoundError(f"No se encuentra la plantilla de prompt: {path}")
    return path.read_text(encoding="utf-8")

# -------------------------
# Utilidades de RAG + LLM
# -------------------------
def _build_query(req: RecipeGenRequest) -> str:
    parts = []
    if req.ingredients:
        parts.append("ingredientes: " + ", ".join(req.ingredients))
    if req.appliances:
        parts.append("electrodomésticos: " + ", ".join(req.appliances))
    if req.dietary:
        parts.append("preferencias: " + ", ".join(req.dietary))
    parts.append(f"raciones: {req.portions}")
    return " | ".join(parts)

def _format_context(hits: List[Dict[str, Any]]) -> str:
    blocks: List[str] = []
    for h in hits:
        p = h.get("payload", {})
        title = p.get("title") or p.get("path") or "doc"
        chunk = p.get("chunk")
        txt = (p.get("text") or "").strip()
        if not txt:
            continue
        head = f"### {title} (chunk {chunk})" if chunk else f"### {title}"
        blocks.append(head + "\n" + txt)
    return "\n\n---\n\n".join(blocks)

def _render_prompt(req: RecipeGenRequest, context: str) -> str:
    tpl = _read_template(req.mode)
    # Requisitos del usuario en texto
    user_bits = []
    if req.ingredients:
        user_bits.append("Ingredientes del usuario: " + ", ".join(req.ingredients))
    if req.dietary:
        user_bits.append("Preferencias del usuario: " + ", ".join(req.dietary))
    if req.appliances:
        user_bits.append("Electrodomésticos del usuario: " + ", ".join(req.appliances))
    user_bits.append(f"Raciones deseadas: {req.portions}")
    user_req = "\n".join(user_bits)

    allowed_appl = req.appliances or ['sartén','horno','airfryer','microondas','robot']
    allowed_appl_str = json.dumps(allowed_appl, ensure_ascii=False)

    filled = tpl.format(
        appliances_allowed=allowed_appl_str,
        portions=req.portions,
        context=context,
        user_requirements=user_req
    )
    return filled

async def _call_llm(prompt: str) -> str:
    return await generate_json(prompt)

def _extract_json(text: str) -> Dict[str, Any]:
    s = text.strip()
    # Limpia fences ```...``` si aparecen
    if s.startswith("```"):
        s = re.sub(r"^```(?:json)?\s*", "", s)
        s = re.sub(r"\s*```$", "", s)
    try:
        return json.loads(s)
    except Exception:
        start = s.find("{"); end = s.rfind("}")
        if start != -1 and end != -1 and end > start:
            return json.loads(s[start:end+1])
        raise

# -------------------------
# Endpoint principal
# -------------------------
@router.post("/generate", response_model=RecipeGenResponse, summary="Generar receta con RAG (modo: strict|hybrid|creative)")
async def generate_recipe(
    req: RecipeGenRequest = Body(...),
    user_id: str = Depends(get_current_user),
):
    # 1) Embeddings de la consulta
    query = _build_query(req)
    emb = await embed_dual([query])

    # 2) Preparar query_vectors
    dims = settings.parsed_vector_dims()
    query_vectors: Dict[str, List[float]] = {}
    for key in dims.keys():  # p.ej. "mxbai","jina"
        vecs = emb.get(key) or []
        if not vecs or not isinstance(vecs[0], list) or len(vecs[0]) != dims[key]:
            continue
        query_vectors[key] = vecs[0]
    if not query_vectors:
        raise HTTPException(500, "Fallo al preparar embeddings de búsqueda (sin vectores válidos).")

    # 3) Búsqueda RAG
    hits = await search(query_vectors, top_k=req.top_k)

    # 4) Contexto y fuentes
    context = _format_context(hits)
    sources: List[SourceHit] = []
    for h in hits:
        p = h.get("payload", {})
        sources.append(SourceHit(
            id=str(h.get("id")),
            score=float(h.get("score", 0.0)),
            title=p.get("title"),
            path=p.get("path"),
            chunk=p.get("chunk"),
            snippet=(p.get("text") or "")[:220]
        ))

    # 5) Render de prompt desde archivo
    try:
        prompt = _render_prompt(req, context)
    except FileNotFoundError as e:
        raise HTTPException(500, str(e))

    # 6) LLM
    raw = await _call_llm(prompt)

    # 7) Parseo/validación
    try:
        data = _extract_json(raw)
        recipe = RecipeNeutral(**{
            "title": data.get("title") or "Receta",
            "portions": int(data.get("portions") or req.portions),
            "steps_generic": data.get("steps_generic") or []
        })
    except Exception:
        # Fallback seguro si el LLM devolviera algo raro
        safe = {
            "title": "Receta generada",
            "portions": req.portions,
            "steps_generic": [
                {
                    "action": "prep",
                    "description": "Preparar ingredientes básicos.",
                    "ingredients": [*req.ingredients],
                    "tools": [],
                    "temperature_c": None,
                    "time_min": 5,
                    "speed": None,
                    "notes": "Fallback: estructura inválida del modelo.",
                    "batching": False
                },
                {
                    "action": "cook",
                    "description": "Cocinar con el electrodoméstico disponible más conveniente.",
                    "ingredients": [*req.ingredients],
                    "tools": req.appliances[:1] if req.appliances else [],
                    "temperature_c": 190 if ("airfryer" in req.appliances) else None,
                    "time_min": 12,
                    "speed": None,
                    "notes": None,
                    "batching": False
                }
            ]
        }
        recipe = RecipeNeutral(**safe)

    return RecipeGenResponse(recipe=recipe, mode=req.mode, sources=sources)
