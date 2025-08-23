import httpx
from typing import List, Dict
from .config import settings

OLLAMA_EMBED_PATH = "/api/embeddings"

async def embed_single(text: str, model: str) -> List[float]:
    async with httpx.AsyncClient(timeout=120) as client:
        r = await client.post(
            settings.ollama_url + OLLAMA_EMBED_PATH,
            json={"model": model, "prompt": text}
        )
        r.raise_for_status()
        data = r.json()
        return data["embedding"]

async def embed_dual(texts: List[str], models: List[str]) -> Dict[str, List[List[float]]]:
    # Devuelve embeddings para cada modelo
    out: Dict[str, List[List[float]]] = {}
    for m in models:
        # Llamadas secuenciales para simplicidad; se puede paralelizar
        vecs = []
        for t in texts:
            vecs.append(await embed_single(t, m))
        out[m] = vecs
    return out
