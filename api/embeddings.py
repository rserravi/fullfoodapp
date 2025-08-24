import httpx
from typing import List, Dict
from .config import settings

ENDPOINTS = [
    ("/api/embeddings", "prompt"),
    ("/api/embeddings", "input"),
    ("/api/embed", "input"),
    ("/api/embed", "prompt"),
]

def _variants(model: str):
    yield model
    if model.startswith("jina/"):
        yield model.split("/", 1)[1]
    elif "jina-embeddings-v2-base-es" in model:
        yield f"jina/{model}"

async def embed_single(text: str, model: str) -> List[float]:
    timeout = settings.ollama_timeout_s
    async with httpx.AsyncClient(timeout=timeout) as client:
        for mdl in _variants(model):
            for path, key in ENDPOINTS:
                payload = {"model": mdl, key: text}
                r = await client.post(settings.ollama_url + path, json=payload)
                if r.status_code == 404:
                    continue
                r.raise_for_status()
                data = r.json()
                if isinstance(data, dict):
                    if "embedding" in data:
                        return data["embedding"]
                    if "embeddings" in data and data["embeddings"]:
                        return data["embeddings"][0]
        raise RuntimeError(f"No pude obtener embeddings. Revisa OLLAMA_URL y el nombre del modelo: {model}")

async def embed_dual(texts: List[str], models: List[str]) -> Dict[str, List[List[float]]]:
    out: Dict[str, List[List[float]]] = {}
    for m in models:
        vecs = []
        for t in texts:
            vecs.append(await embed_single(t, m))
        out[m] = vecs
    return out
