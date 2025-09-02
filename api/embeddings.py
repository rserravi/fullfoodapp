from __future__ import annotations
from typing import List, Dict, Optional
import httpx
from .config import settings

def _short_key(model_name: str) -> str:
    name = model_name.lower()
    if "mxbai" in name:
        return "mxbai"
    if "jina" in name:
        return "jina"
    return name.replace(":", "_").replace("/", "_")

# Posibles endpoints de embeddings
EMBED_ENDPOINTS = ("/api/embed", "/api/embeddings")  # primero el oficial

async def _embed_call(client: httpx.AsyncClient, model: str, inp):
    """
    Llama al endpoint de embeddings de Azure OpenAI con 'input'.
    Devuelve el JSON ya cargado.
    """
    base = settings.azure_openai_endpoint.rstrip("/")
    payload = {"model": model, "input": inp}
    last_exc = None
    for ep in EMBED_ENDPOINTS:
        try:
            r = await client.post(base + ep, json=payload)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            last_exc = e
            continue
    raise last_exc or RuntimeError("No se pudo invocar al endpoint de embeddings")

def _parse_embed_response(data, expect_batch: bool) -> List[List[float]]:
    """
    Normaliza la respuesta:
    - single: {"embeddings":[...]} -> [[...]]
    - batch:  {"embeddings":[[...],[...],...]} -> tal cual
    - compat: {"data":[{"embedding":[...]}]}   -> idem
    """
    # Formato oficial Azure OpenAI
    if isinstance(data, dict) and "embeddings" in data:
        emb = data["embeddings"]
        if not isinstance(emb, list):
            raise ValueError("Campo 'embeddings' inválido")
        # single → lista de floats; batch → lista de listas
        if emb and isinstance(emb[0], (int, float)):
            return [emb]
        return emb

    # Compat con otras variantes
    if isinstance(data, dict) and "data" in data and isinstance(data["data"], list):
        arr = []
        for item in data["data"]:
            v = item.get("embedding")
            if not isinstance(v, list):
                v = []
            arr.append(v)
        return arr

    # Si llega aquí, devolvemos vacío para forzar fallback / chequeo aguas arriba
    return [[]] if not expect_batch else [[] for _ in range(1 if not expect_batch else 0)]

async def _post_embeddings_batch(model: str, inputs: List[str]) -> List[List[float]]:
    """
    Intento batch. Si el backend no soporta batch o devuelve tamaños inesperados,
    llamamos per-item.
    """
    timeout = settings.azure_openai_timeout_s
    async with httpx.AsyncClient(timeout=timeout) as client:
        try:
            data = await _embed_call(client, model, inputs)
            vecs = _parse_embed_response(data, expect_batch=True)
            # Validación simple: tamaño debe coincidir
            if isinstance(vecs, list) and len(vecs) == len(inputs) and all(isinstance(v, list) for v in vecs):
                return vecs
        except Exception:
            pass

        # Fallback per-item
        out: List[List[float]] = []
        for t in inputs:
            data = await _embed_call(client, model, t)
            vecs = _parse_embed_response(data, expect_batch=False)
            v = vecs[0] if vecs else []
            out.append(v if isinstance(v, list) else [])
        return out

async def embed_single(text: str, model: str) -> List[float]:
    vecs = await _post_embeddings_batch(model, [text])
    return vecs[0] if vecs else []

async def embed_batch(texts: List[str], model: str) -> List[List[float]]:
    return await _post_embeddings_batch(model, texts)

async def embed_dual(texts: List[str], models: Optional[List[str]] = None) -> Dict[str, List[List[float]]]:
    models = models or settings.parsed_embedding_models()
    out: Dict[str, List[List[float]]] = {}
    for m in models:
        vecs = await embed_batch(texts, m)
        out[_short_key(m)] = vecs
    return out
