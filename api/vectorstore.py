from __future__ import annotations
from typing import List, Dict, Any, Iterable, Optional
from uuid import uuid4

from qdrant_client import QdrantClient
from qdrant_client.models import VectorParams, Distance, PointStruct

from .config import settings

def _client() -> QdrantClient:
    return QdrantClient(url=settings.qdrant_url, timeout=settings.rag_timeout_s)

async def ensure_collection(vector_dims: Optional[Dict[str, int]] = None) -> None:
    """
    Asegura la colección multi-vector. Si no existe, la crea.
    Nota: no recrea si ya existe (evita pérdidas accidentales).
    """
    client = _client()
    name = settings.collection_name
    dims = vector_dims or settings.parsed_vector_dims()
    if client.collection_exists(name):
        return
    cfg = {k: VectorParams(size=v, distance=Distance.COSINE) for k, v in dims.items()}
    client.create_collection(collection_name=name, vectors_config=cfg)

def _expected_vector_names() -> List[str]:
    # Debe coincidir con settings.vector_dims (p.ej. "mxbai:1024,jina:768")
    return list(settings.parsed_vector_dims().keys())

def upsert_documents(texts: List[str], payloads: List[Dict[str, Any]], embeddings: Dict[str, List[List[float]]]) -> None:
    """
    Inserta/actualiza puntos multi-vector en Qdrant.
    - Valida que existan todas las claves esperadas (p.ej. "mxbai","jina").
    - Omite documentos cuyos embeddings vengan vacíos o desalineados.
    """
    assert len(texts) == len(payloads), "texts y payloads deben tener igual longitud"
    client = _client()
    name = settings.collection_name
    expected = _expected_vector_names()

    n = len(texts)
    # Validación de presencia y conteo
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
            # vec debe ser lista con longitud > 0
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

        points.append(PointStruct(
            id=str(uuid4()),
            vector=vec_dict,     # dict { "mxbai": [...], "jina": [...] }
            payload=payload
        ))

    if points:
        client.upsert(collection_name=name, points=points)
    if skipped:
        print(f"[vectorstore] Aviso: omitidos {skipped} documento(s) por embeddings vacíos/invalidos.")

def search(query_vectors: Dict[str, List[float]], top_k: int = 5) -> List[Dict[str, Any]]:
    """
    Búsqueda por múltiples vectores: devuelve los mejores resultados mergeados por score.
    Estrategia simple: buscar por la primera clave y usar 'score' devuelto.
    """
    client = _client()
    name = settings.collection_name
    # Elegimos una clave principal (la primera de expected que exista en la query)
    expected = _expected_vector_names()
    primary = next((k for k in expected if k in query_vectors), None)
    if not primary:
        raise ValueError(f"No hay vectores de consulta válidos. Esperados alguno de {expected}, recibido {list(query_vectors.keys())}")
    res = client.search(
        collection_name=name,
        query_vector=(primary, query_vectors[primary]),
        limit=top_k,
        with_payload=True
    )
    # Normaliza a dicts sencillos
    out: List[Dict[str, Any]] = []
    for r in res:
        out.append({
            "id": r.id,
            "score": float(r.score),
            "payload": r.payload
        })
    return out
