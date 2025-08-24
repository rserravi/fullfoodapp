from fastapi import FastAPI, HTTPException
from fastapi.responses import ORJSONResponse
from typing import List, Dict
import json
from .config import settings
from .schemas import IngestRequest, SearchRequest, SearchResponse, SearchHit, RecipeGenRequest, RecipeNeutral, RecipePlan
from .embeddings import embed_dual, embed_single
from .vectorstore import ensure_collection, upsert_documents, search
from .compiler.compiler import compile_recipe
from .rag import hybrid_retrieve, build_context
from .llm import generate_json

app = FastAPI(default_response_class=ORJSONResponse, title="FullFoodApp API")

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
    # Mapea nombre de vector → modelo real (por ahora fijo, documentar en README)
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

    # 2) Build prompt from template
    tmpl_path = "prompts/recipe_generation.md"
    try:
        with open(tmpl_path, "r", encoding="utf-8") as f:
            tmpl = f.read()
    except FileNotFoundError:
        raise HTTPException(status_code=500, detail="No se encuentra la plantilla de prompt.")

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

    # 4) Parse & validate
    try:
        data = json.loads(raw_json)
        recipe = RecipeNeutral(**data)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"JSON inválido devuelto por el LLM: {e}. Resp: {raw_json[:200]}...")

    # 5) Compile to appliances
    plans = compile_recipe(recipe, req.appliances)
    if not plans:
        raise HTTPException(status_code=400, detail="Ningún electrodoméstico soportado en la petición.")
    return RecipePlan(recipe=recipe, plans=plans)