from __future__ import annotations
from typing import List, Dict, Optional
from openai import AsyncAzureOpenAI

from .config import settings


def _short_key(model_name: str) -> str:
    name = model_name.lower()
    if "mxbai" in name:
        return "mxbai"
    if "jina" in name:
        return "jina"
    return name.replace(":", "_").replace("/", "_")


_client: Optional[AsyncAzureOpenAI] = None


def _get_client() -> AsyncAzureOpenAI:
    global _client
    if _client is None:
        _client = AsyncAzureOpenAI(
            api_key=settings.azure_openai_api_key,
            api_version=settings.azure_openai_api_version,
            azure_endpoint=settings.azure_openai_endpoint,
        )
    return _client


async def _post_embeddings_batch(model: str, inputs: List[str]) -> List[List[float]]:
    """Obtiene embeddings en batch desde Azure OpenAI.
    Si hay error o el tamaño no coincide, intenta per-item."""

    client = _get_client()
    try:
        res = await client.embeddings.create(model=model, input=inputs)
        data = getattr(res, "data", [])
        vecs = [d.embedding for d in data]
        if len(vecs) == len(inputs):
            return vecs
    except Exception:
        pass

    out: List[List[float]] = []
    for t in inputs:
        try:
            r = await client.embeddings.create(model=model, input=[t])
            emb = r.data[0].embedding if r.data else []
        except Exception:
            emb = []
        out.append(emb)
    return out


async def embed_single(text: str, model: str) -> List[float]:
    vecs = await embed_batch([text], model)
    return vecs[0] if vecs else []


async def embed_batch(texts: List[str], model: str) -> List[List[float]]:
    return await _post_embeddings_batch(model, texts)

async def embed_dual(texts: List[str], models: Optional[List[str]] = None) -> Dict[str, List[List[float]]]:
    models = models or settings.parsed_embedding_models()
    out: Dict[str, List[List[float]]] = {}
    for m in models:
        out[m] = await embed_batch(texts, m)
    return out

