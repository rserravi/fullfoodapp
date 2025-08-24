from __future__ import annotations
from typing import List, Dict, Any, Tuple
from uuid import uuid4
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct, Filter, FieldCondition, MatchValue
import httpx

from .config import settings

_client = QdrantClient(url=settings.qdrant_url, timeout=settings.rag_timeout_s)

def _vec_cfg() -> Dict[str, VectorParams]:
    cfg: Dict[str, VectorParams] = {}
    for name, dim in settings.parsed_vector_dims().items():
        cfg[name] = VectorParams(size=dim, distance=Distance.COSINE)
    return cfg

@retry(reraise=True, stop=stop_after_attempt(3), wait=wait_exponential(min=0.2, max=2), retry=retry_if_exception_type(Exception))
async def ensure_collection(vector_dims: Dict[str, int]):
    name = settings.collection_name
    exists = _client.collection_exists(name)
    if not exists:
        _client.recreate_collection(
            collection_name=name,
            vectors_config=_vec_cfg()
        )

async def upsert_documents(texts: List[str], payloads: List[Dict[str, Any]], embeddings: Dict[str, List[List[float]]]):
    points: List[PointStruct] = []
    name_map = { "mxbai-embed-large": "mxbai", "jina/jina-embeddings-v2-base-es": "jina", "mxbai": "mxbai", "jina": "jina" }
    for i, text in enumerate(texts):
        vec_dict: Dict[str, List[float]] = { name_map[k]: embeddings[k][i] for k in embeddings }
        points.append(PointStruct(
            id=str(uuid4()),
            vector=vec_dict,
            payload=payloads[i] | {"text": text}
        ))
    _client.upsert(collection_name=settings.collection_name, points=points)

async def search(query_vecs: Dict[str, List[float]], top_k: int = 5, filters: Dict[str, Any] | None = None) -> List[Dict[str, Any]]:
    """
    Multi-vector search: hace una búsqueda por cada vector y fusiona resultados simples.
    """
    all_hits: List[Tuple[str, float, Dict[str, Any]]] = []
    for vec_name, vec in query_vecs.items():
        res = _client.search(
            collection_name=settings.collection_name,
            query_vector=(vec_name, vec),
            limit=top_k,
        )
        for hit in res:
            all_hits.append((hit.id, float(hit.score), hit.payload))
    # ordenar por score desc y desduplicar por id
    seen = set()
    out: List[Dict[str, Any]] = []
    for pid, score, payload in sorted(all_hits, key=lambda x: x[1], reverse=True):
        if pid in seen:
            continue
        seen.add(pid)
        out.append({"id": pid, "score": score, "payload": payload})
    return out
