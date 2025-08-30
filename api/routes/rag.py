from __future__ import annotations
from typing import List
from fastapi import APIRouter, Depends, HTTPException, Body, Query
from qdrant_client import QdrantClient
from qdrant_client.models import VectorParams, Distance
from typing import List, Dict

from ..config import settings
from ..security import get_current_user
from ..schemas import Document, IngestRequest, SearchRequest, SearchResponse, SearchHit
from ..embeddings import embed_dual
from ..vectorstore import upsert_documents, search
from ..errors import ErrorResponse

router = APIRouter(prefix="/rag", tags=["rag"])

@router.post(
    "/ingest",
    summary="Ingerir documentos (JSON)",
    responses={200: {"description": "OK"}, 400: {"model": ErrorResponse}},
)
async def rag_ingest(
    req: IngestRequest = Body(...),
    user_id: str = Depends(get_current_user),
):
    if not req.documents:
        raise HTTPException(400, "documents vacío")
    texts: List[str] = []
    payloads: List[dict] = []
    for d in req.documents:
        texts.append(d.text)
        md = (d.metadata or {}).copy()
        md["user_id"] = user_id
        if d.id:
            md["source_id"] = d.id
        payloads.append(md)
    embs = await embed_dual(texts)
    await upsert_documents(texts, payloads, embs)
    return {"ok": True, "ingested": len(texts)}

@router.post(
    "/search",
    response_model=SearchResponse,
    summary="Buscar en RAG (embeddings + multi-vector)",
)
# ... imports y modelos arriba ...

@router.post("/search", summary="Búsqueda híbrida en RAG")
async def rag_search(req: SearchRequest = Body(...), user_id: str = Depends(get_current_user)):
    # 1) Embeddings de la query
    emb = await embed_dual([req.query])
    dims = settings.parsed_vector_dims()

    # 2) Construye el dict de vectores válidos
    qvecs: Dict[str, List[float]] = {}
    for key in dims.keys():  # p.ej. "mxbai", "jina"
        vecs = emb.get(key) or []
        if vecs and isinstance(vecs[0], list) and len(vecs[0]) == dims[key]:
            qvecs[key] = vecs[0]

    if not qvecs:
        raise HTTPException(500, "No se obtuvieron embeddings válidos para la consulta.")

    # 3) Búsqueda en Qdrant
    hits = await search(qvecs, top_k=req.top_k)

    # 4) Normaliza la respuesta
    out = []
    for h in hits:
        p = h.get("payload", {})
        out.append({
            "id": h.get("id"),
            "score": h.get("score"),
            "title": p.get("title"),
            "path": p.get("path"),
            "chunk": p.get("chunk"),
            "text": p.get("text"),
        })
    return {"results": out}


@router.get(
    "/count",
    summary="Contar puntos en la colección",
)
def rag_count(
    user_id: str = Depends(get_current_user),
):
    client = QdrantClient(url=settings.qdrant_url, timeout=settings.rag_timeout_s)
    res = client.count(collection_name=settings.collection_name, exact=True)
    return {"collection": settings.collection_name, "count": res.count}

@router.delete(
    "/clear",
    summary="Vaciar colección (opcionalmente recrear)",
    responses={200: {"description": "OK"}, 400: {"model": ErrorResponse}},
)
def rag_clear(
    recreate: bool = Query(True, description="Si true, recrea la colección con la misma config"),
    user_id: str = Depends(get_current_user),
):
    client = QdrantClient(url=settings.qdrant_url, timeout=settings.rag_timeout_s)
    if recreate:
        # recrea con la configuración multivector
        dims = settings.parsed_vector_dims()
        cfg = {}
        for name, dim in dims.items():
            cfg[name] = VectorParams(size=dim, distance=Distance.COSINE)
        client.recreate_collection(collection_name=settings.collection_name, vectors_config=cfg)
    else:
        client.delete_collection(settings.collection_name)
    return {"ok": True, "recreated": recreate, "collection": settings.collection_name}
