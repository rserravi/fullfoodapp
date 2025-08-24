from qdrant_client import QdrantClient
from qdrant_client.http import models as qmodels
from typing import List, Dict
from .config import settings
import uuid

client = QdrantClient(url=settings.qdrant_url)

async def ensure_collection(vector_dims: Dict[str, int]):
    vectors_config = {name: qmodels.VectorParams(size=dim, distance=qmodels.Distance.COSINE)
                      for name, dim in vector_dims.items()}
    try:
        client.get_collection(settings.collection_name)
    except Exception:
        client.recreate_collection(
            collection_name=settings.collection_name,
            vectors_config=vectors_config,
        )

async def upsert_documents(texts: List[str], payloads: List[Dict], embeddings: Dict[str, List[List[float]]]):
    name_map = {
        "mxbai-embed-large": "mxbai",
        "jina-embeddings-v2-base-es": "jina"
    }
    points = []
    for i, text in enumerate(texts):
        pid = payloads[i].get("id") or str(uuid.uuid4())
        vec_dict = { name_map[k]: embeddings[k][i] for k in embeddings }
        point = qmodels.PointStruct(
            id=pid,
            vector=vec_dict,
            payload={
                **payloads[i],
                "text": text,
            }
        )
        points.append(point)
    client.upsert(settings.collection_name, points=points)

async def search(query: str, query_vector: List[float], vector_name: str, top_k: int):
    res = client.search(
        collection_name=settings.collection_name,
        query_vector=(vector_name, query_vector),
        limit=top_k,
        with_payload=True
    )
    return res
