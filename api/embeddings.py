from __future__ import annotations
from typing import List, Dict, Optional
import httpx

from .config import settings

async def embed_batch(texts: List[str], model: str) -> List[List[float]]:
    """Obtiene embeddings de Azure OpenAI para una lista de textos."""
    base = settings.azure_openai_endpoint.rstrip("/")
    url = f"{base}/openai/deployments/{model}/embeddings?api-version={settings.azure_openai_api_version}"
    payload = {"input": texts}
    headers = {"api-key": settings.azure_openai_api_key}
    timeout = settings.llm_timeout_s
    async with httpx.AsyncClient(timeout=timeout) as client:
        r = await client.post(url, json=payload, headers=headers)
        r.raise_for_status()
        data = r.json()
        return [item.get("embedding", []) for item in data.get("data", [])]

async def embed_single(text: str, model: str) -> List[float]:
    vecs = await embed_batch([text], model)
    return vecs[0] if vecs else []

async def embed_dual(texts: List[str], models: Optional[List[str]] = None) -> Dict[str, List[List[float]]]:
    models = models or settings.parsed_embedding_models()
    out: Dict[str, List[List[float]]] = {}
    for m in models:
        out[m] = await embed_batch(texts, m)
    return out
