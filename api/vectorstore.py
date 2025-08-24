from qdrant_client import QdrantClient
from qdrant_client.http import models as qmodels
from typing import List, Dict, Any
from .config import settings
import uuid

client = QdrantClient(url=settings.qdrant_url)

def model_to_vector_key(model: str) -> str:
    """Normaliza nombre de modelo → clave de vector definida en .env (mxbai/jina)."""
    m = model.lower()
    if "mxbai" in m:
        return "mxbai"
    if "jina-embeddings-v2-base-es" in m:
        return "jina"
    return m.split("/")[-1].split(":")[0]

def to_point_id(orig_id: Any) -> Any:
    """Convierte un id arbitrario a entero o UUID (string) aceptado por Qdrant."""
    if orig_id is None:
        return str(uuid.uuid4())
    # ¿Es un entero?
    try:
        return int(orig_id)
    except Exception:
        pass
    # ¿Es un UUID válido?
    try:
        return str(uuid.UUID(str(orig_id)))
    except Exception:
        # UUID determinista basado en el id original (estable entre ingestas)
        return str(uuid.uuid5(uuid.NAMESPACE_URL, f"fullfoodapp:{orig_id}"))

# Crea/recrea la colección con vectores nombrados según .env
async def ensure_collection(vector_dims: Dict[str, int]):
    vectors_config = {
        name: qmodels.VectorParams(size=dim, distance=qmodels.Distance.COSINE)
        for name, dim in vector_dims.items()
    }
    try:
        client.get_collection(settings.collection_name)
    except Exception:
        client.recreate_collection(
            collection_name=settings.collection_name,
            vectors_config=vectors_config,
        )

async def upsert_documents(texts: List[str], payloads: List[Dict], embeddings: Dict[str, List[List[float]]]):
    points = []
    for i, text in enumerate(texts):
        payload = dict(payloads[i])  # copia
        orig_id = payload.pop("id", None)  # <- no usarlo como point-id directamente
        if orig_id is not None:
            payload["doc_id"] = orig_id

        # Construye diccionario de vectores con claves normalizadas (mxbai/jina)
        vec_dict: Dict[str, List[float]] = {}
        for model_name, vecs in embeddings.items():
            key = model_to_vector_key(model_name)
            vec_dict[key] = vecs[i]

        point = qmodels.PointStruct(
            id=to_point_id(orig_id),
            vector=vec_dict,
            payload={**payload, "text": text},
        )
        points.append(point)

    client.upsert(settings.collection_name, points=points)

async def search(query: str, query_vector: List[float], vector_name: str, top_k: int):
    return client.search(
        collection_name=settings.collection_name,
        query_vector=(vector_name, query_vector),
        limit=top_k,
        with_payload=True,
    )