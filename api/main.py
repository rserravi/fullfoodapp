from fastapi import FastAPI
from fastapi.responses import ORJSONResponse
from typing import List, Dict
from .config import settings
from .schemas import IngestRequest, SearchRequest, SearchResponse, SearchHit, RecipeGenRequest, RecipeNeutral, RecipePlan
from .embeddings import embed_dual, embed_single
from .vectorstore import ensure_collection, upsert_documents, search
from .compiler.compiler import compile_recipe

app = FastAPI(default_response_class=ORJSONResponse, title="FullFoodApp API")

@app.on_event("startup")
async def startup():
    # Detectar dimensiones dinámicamente
    models = settings.embedding_models.split(',')
    dummy = "test"
    dims = {}
    for m in models:
        vec = await embed_single(dummy, m)
        dims[m] = len(vec)
    # Mapear a nombres de vector en Qdrant
    name_map = {
        "mxbai-embed-large": "mxbai",
        "jina-embeddings-v2-base-es": "jina"
    }
    vector_dims = { name_map[k]: v for k, v in dims.items() }
    await ensure_collection(vector_dims)

@app.get("/health")
async def health():
    return {"status": "ok", "qdrant": settings.qdrant_url}

@app.post("/ingest")
async def ingest(req: IngestRequest):
    texts = [d.text for d in req.documents]
    payloads: List[Dict] = []
    for d in req.documents:
        payload = {**d.metadata}
        if d.id:
            payload["id"] = d.id
        payloads.append(payload)
    models = settings.embedding_models.split(',')
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
    model_map = {"mxbai": "mxbai-embed-large", "jina": "jina-embeddings-v2-base-es"}
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

# Stub generación de receta neutra y compilación
@app.post("/recipes/generate", response_model=RecipePlan)
async def gen_recipe(req: RecipeGenRequest):
    # MVP: receta neutra fija de ejemplo (sustituir por pipeline RAG + LLM)
    recipe = RecipeNeutral(
        title="Verduras asadas crujientes",
        portions=req.portions,
        steps_generic=[
            {"action":"prep","description":"Corta calabacín y pimiento en dados; seca con papel.","ingredients":["calabacín","pimiento"],"tools":["cuchillo"],"temperature_c":None,"time_min":None,"speed":None,"notes":None,"batching":False},
            {"action":"season","description":"Mezcla con aceite de oliva, sal, pimienta y ajo en polvo.","ingredients":["aceite","sal","pimienta","ajo en polvo"],"tools":["bol"],"temperature_c":None,"time_min":None,"speed":None,"notes":None,"batching":False},
            {"action":"cook","description":"Cocina hasta dorar los bordes.","ingredients":[],"tools":[],"temperature_c":200,"time_min":12,"speed":None,"notes":"remover a mitad","batching":False},
            {"action":"serve","description":"Termina con perejil picado y sirve caliente.","ingredients":["perejil"],"tools":[],"temperature_c":None,"time_min":None,"speed":None,"notes":None,"batching":False}
        ]
    )
    plans = compile_recipe(recipe, req.appliances)
    return RecipePlan(recipe=recipe, plans=plans)
