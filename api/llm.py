from __future__ import annotations
import asyncio
import json
from typing import Any, Dict, Optional
import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from .config import settings

# Semáforo global para limitar concurrencia
_llm_semaphore = asyncio.Semaphore(settings.llm_max_concurrency)

class LLMError(RuntimeError):
    pass

@retry(
    reraise=True,
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=0.5, min=0.5, max=4),
    retry=retry_if_exception_type((httpx.TimeoutException, httpx.TransportError, LLMError)),
)
async def _azure_generate(prompt: str, model: str, temperature: float, max_tokens: int) -> str:
    """
    Llama a Azure OpenAI con stream=false y devuelve el campo 'response' (texto).
    """
    url = f"{settings.azure_openai_endpoint.rstrip('/')}/api/generate"
    payload: Dict[str, Any] = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": temperature,
            "num_predict": max_tokens
        }
    }
    timeout = settings.llm_timeout_s
    async with httpx.AsyncClient(timeout=timeout) as client:
        r = await client.post(url, json=payload)
        if r.status_code >= 500:
            raise LLMError(f"Azure OpenAI 5xx: {r.status_code}")
        r.raise_for_status()
        data = r.json()
        if not isinstance(data, dict) or "response" not in data:
            raise LLMError("Respuesta inválida de Azure OpenAI")
        return str(data["response"])

async def generate_json(prompt: str, model: Optional[str] = None, temperature: float = 0.2, max_tokens: int = 1024) -> str:
    """
    Genera texto (esperado JSON) usando Azure OpenAI, con límite de concurrencia.
    """
    mdl = model or settings.azure_openai_deployment_llm
    async with _llm_semaphore:
        text = await _azure_generate(prompt=prompt, model=mdl, temperature=temperature, max_tokens=max_tokens)
        return text
