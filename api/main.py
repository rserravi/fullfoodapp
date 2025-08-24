from fastapi import FastAPI, HTTPException
from fastapi.responses import ORJSONResponse
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Dict
from pathlib import Path
import json

from .config import settings
from .schemas import (
    IngestRequest, SearchRequest, SearchResponse, SearchHit,
    RecipeGenRequest, RecipeNeutral, RecipePlan
)
from .embeddings import embed_dual, embed_single
from .vectorstore import ensure_collection, upsert_documents, search
from .compiler.compiler import compile_recipe
from .rag import hybrid_retrieve, build_context
from .llm import generate_json
from .utils.json_repair import repair_json_minimal, repair_via_llm

app = FastAPI(default_response_class=ORJSONResponse, title="FullFoodApp API")

# --- CORS desde .env ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_allow_origins.split(",")] if settings.cors_allow_origins != "*" else ["*"],
    allow_credentials=settings.cors_allow_credentials,
    allow_methods=[m.strip() for m in settings.cors_allow_methods.split(",")] if settings.cors_allow_methods != "*" else ["*"],
    allow_headers=[h.strip() for h in settings.cors_allow_headers.split(",")] if settings.cors_allow_headers != "*" else ["*"],
)

@app.on_event("startup")
async def startup():
    # No dependemos de Ollama aquí; tomamos dimensiones desde .env
    vector_dims = settings.parsed_vector_dims()  # ej: {"mxbai":1024, "jina":768}
    await ensure_collection(vector_dims)

@app.get("/health")
async def health():
    return {"status": "ok", "qdrant": settings.qdrant_url, "llm": settings.llm_model}

@app.post("/ingest")
async def ingest(req: IngestRequest):
    texts = [d.text for d in req.documents]
    payloads: List[Dict] = []
    for d in req.documents:
        payload = {**d.metadata}
        if d.id:
            payload["id"] = d.id
        payloads.append(payload)
    models = settings.parsed_embedding_models()
    embs = await embed_dual(texts, models)
    await upsert_documents(texts, payloads, embs)
    return {"ok": True, "count": len(texts)}

# Heurística simple para elegir vector por idioma
SPANISH_MARKERS = {" el ", " la ", " de ", " y ", " con ", " para ", " receta ", " ingredientes ", " minutos "}

def choose_vector(query: str, requested: str) -> str:
    if requested in ("mxbai", "jina"):
        return requested
    q = f" {query.lower()} "
    return "jina" if any(tok in q for tok in SPANISH_MARKERS) else "mxbai"

@app.post("/search", response_model=SearchResponse)
async def search_route(req: SearchRequest):
    vector_name = choose_vector(req.query, req.vector)
    # mapea nombre de vector → modelo real (ajustable si añades más)
    model_map = {"mxbai": "mxbai-embed-large", "jina": "jina/jina-embeddings-v2-base-es"}
    vec = await embed_single(req.query, model_map[vector_name])
    hits = await search(req.query, vec, vector_name, req.top_k)
    out = [
        SearchHit(
            id=str(h.id),
            score=h.score,
            text=h.payload.get("text", ""),
            metadata={k: v for k, v in h.payload.items() if k != "text"}
        ) for h in hits
    ]
    return SearchResponse(hits=out)

@app.post("/recipes/generate", response_model=RecipePlan)
async def gen_recipe(req: RecipeGenRequest):
    # 1) Retrieve
    query = ", ".join(req.ingredients) or "receta sencilla"
    hits = await hybrid_retrieve(query, top_k_each=5)
    if not hits:
        raise HTTPException(status_code=404, detail="No hay contexto para RAG; ingesta vacía.")

    context = build_context(hits)

    # 2) Build prompt from template (ruta robusta)
    tmpl_path = Path(__file__).resolve().parent / "prompts" / "recipe_generation.md"
    if not tmpl_path.exists():
        raise HTTPException(status_code=500, detail=f"No se encuentra la plantilla de prompt en: {tmpl_path}")
    tmpl = tmpl_path.read_text(encoding="utf-8")

    prompt = (tmpl
        .replace("{{ingredients}}", ", ".join(req.ingredients))
        .replace("{{portions}}", str(req.portions))
        .replace("{{dietary}}", ", ".join(req.dietary) if req.dietary else "ninguna")
        .replace("{{context}}", context)
    )

    # 3) Call LLM (JSON enforced)
    try:
        raw_json = await generate_json(prompt, model=settings.llm_model, temperature=0.2, max_tokens=1200)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Fallo al llamar al LLM: {e}")

    # 4) Parse & validate (auto-repair si hace falta)
    try:
        data = json.loads(raw_json)
    except Exception:
        ok, repaired = repair_json_minimal(raw_json)
        if ok:
            data = json.loads(repaired)
        else:
            try:
                repaired_llm = await repair_via_llm(raw_json)
                data = json.loads(repaired_llm)
            except Exception as e:
                snippet = (raw_json or "")[:200]
                raise HTTPException(status_code=500, detail=f"JSON inválido devuelto por el LLM y no se pudo reparar: {e}. Resp: {snippet}...")

    try:
        recipe = RecipeNeutral(**data)
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"El JSON no valida contra el esquema: {e}")

    # 5) Compile to appliances
    plans = compile_recipe(recipe, req.appliances)
    if not plans:
        raise HTTPException(status_code=400, detail="Ningún electrodoméstico soportado en la petición.")
    return RecipePlan(recipe=recipe, plans=plans)
