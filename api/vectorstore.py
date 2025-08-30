from __future__ import annotations
from typing import List, Dict, Any, Optional
from uuid import uuid4

from qdrant_client import QdrantClient
from qdrant_client.models import VectorParams, Distance, PointStruct
from qdrant_client.http import models as qm

from .config import settings

# -------- Qdrant client (singleton) --------
_qc: Optional[QdrantClient] = None

def get_client() -> QdrantClient:
    """Return a singleton Qdrant client."""
    global _qc
    if _qc is None:
        _qc = QdrantClient(
            url=getattr(settings, "qdrant_url", None),
            host=getattr(settings, "qdrant_host", None),
            port=getattr(settings, "qdrant_port", None),
            api_key=getattr(settings, "qdrant_api_key", None),
            timeout=getattr(settings, "rag_timeout_s", None),
        )
    return _qc

# -------- Collection management --------
async def ensure_collection(vector_dims: Optional[Dict[str, int]] = None) -> None:
    """
    Ensure the named-vectors collection exists. If not, create it.
    """
    client = get_client()
    name = settings.collection_name
    dims = vector_dims or settings.parsed_vector_dims()
    if client.collection_exists(name):
        return
    cfg = {k: VectorParams(size=v, distance=Distance.COSINE) for k, v in dims.items()}
    client.create_collection(collection_name=name, vectors_config=cfg)

def _expected_vector_names() -> List[str]:
    # Must match settings.vector_dims (e.g., "mxbai:1024,jina:768")
    return list(settings.parsed_vector_dims().keys())

# -------- Upsert --------
def upsert_documents(
    texts: List[str],
    payloads: List[Dict[str, Any]],
    embeddings: Dict[str, List[List[float]]],
) -> None:
    """
    Insert/update multi-vector points in Qdrant.
    Skips documents with empty/invalid embeddings.
    """
    assert len(texts) == len(payloads), "texts y payloads deben tener igual longitud"
    client = get_client()
    name = settings.collection_name
    expected = _expected_vector_names()

    n = len(texts)
    # Validate presence and counts
    for k in expected:
        if k not in embeddings:
            raise ValueError(f"Faltan embeddings para la clave '{k}'. Claves recibidas: {list(embeddings.keys())}")
        if len(embeddings[k]) != n:
            raise ValueError(f"Desalineación en '{k}': esperados {n} vectores, recibidos {len(embeddings[k])}")

    points: List[PointStruct] = []
    skipped = 0

    for i in range(n):
        vec_dict: Dict[str, List[float]] = {}
        valid = True
        for k in expected:
            vec = embeddings[k][i]
            if not isinstance(vec, list) or len(vec) == 0:
                valid = False
                break
            vec_dict[k] = vec

        if not valid:
            skipped += 1
            continue

        payload = (payloads[i] or {}).copy()
        payload["text"] = texts[i]
        payload.setdefault("user_id", payload.get("user_id", "default"))

        points.append(
            PointStruct(
                id=str(uuid4()),
                vector=vec_dict,     # {"mxbai": [...], "jina": [...]}
                payload=payload,
            )
        )

    if points:
        client.upsert(collection_name=name, points=points)
    if skipped:
        print(f"[vectorstore] Aviso: omitidos {skipped} documento(s) por embeddings vacíos/invalidos.")

# -------- Search --------
def search(query_vectors: Dict[str, List[float]], top_k: int = 5) -> List[Dict[str, Any]]:
    """
    Multi-vector search (simple strategy: query using first available named vector).
    """
    client = get_client()
    name = settings.collection_name
    expected = _expected_vector_names()
    primary = next((k for k in expected if k in query_vectors), None)
    if not primary:
        raise ValueError(
            f"No hay vectores de consulta válidos. Esperados alguno de {expected}, "
            f"recibido {list(query_vectors.keys())}"
        )

    res = client.search(
        collection_name=name,
        query_vector=(primary, query_vectors[primary]),
        limit=top_k,
        with_payload=True,
    )

    out: List[Dict[str, Any]] = []
    for r in res:
        out.append(
            {
                "id": r.id,
                "score": float(r.score),
                "payload": r.payload,
            }
        )
    return out

# -------- Delete (user recipe vectors) --------
def delete_user_recipe_vectors(user_id: str, recipe_id: str) -> None:
    """
    Delete all Qdrant points for a given user recipe based on payload filters.
    """
    client = get_client()
    client.delete(
        collection_name=settings.collection_name,
        points_selector=qm.Filter(
            must=[
                qm.FieldCondition(key="kind", match=qm.MatchValue(value="user_recipe")),
                qm.FieldCondition(key="user_id", match=qm.MatchValue(value=user_id)),
                qm.FieldCondition(key="recipe_id", match=qm.MatchValue(value=recipe_id)),
            ]
        ),
    )
