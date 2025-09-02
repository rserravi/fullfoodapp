from __future__ import annotations
import asyncio
from typing import Any, Dict, Optional
from openai import AsyncAzureOpenAI, APIError, APIConnectionError
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from .config import settings

# Semáforo global para limitar concurrencia
_llm_semaphore = asyncio.Semaphore(settings.llm_max_concurrency)

# Cliente global de Azure OpenAI
_azure_client = AsyncAzureOpenAI(
    azure_endpoint=settings.azure_openai_endpoint,
    api_key=settings.azure_openai_api_key,
    api_version=settings.azure_openai_api_version,
)

class LLMError(RuntimeError):
    pass

@retry(
    reraise=True,
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=0.5, min=0.5, max=4),
    retry=retry_if_exception_type((APIConnectionError, APIError, LLMError)),
)
async def _azure_generate(prompt: str, model: str, temperature: float, max_tokens: int) -> str:
    """
    Llama a Azure OpenAI Chat Completions y devuelve el contenido generado.
    """
    try:
        resp = await _azure_client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=temperature,
            max_tokens=max_tokens,
        )
    except APIError as e:
        status = getattr(e, "status_code", None)
        if status and status >= 500:
            raise LLMError(f"Azure OpenAI 5xx: {status}") from e
        raise

    content = None
    if getattr(resp, "choices", None):
        msg = resp.choices[0].message
        if msg and getattr(msg, "content", None) is not None:
            content = msg.content
    if content is None:
        raise LLMError("Respuesta inválida de Azure OpenAI")
    return str(content)

async def generate_json(prompt: str, model: Optional[str] = None, temperature: float = 0.2, max_tokens: int = 1024) -> str:
    """
    Genera texto (esperado JSON) usando Azure OpenAI, con límite de concurrencia.
    """

    mdl = model or settings.azure_openai_llm_deployment
    async with _llm_semaphore:
        text = await _azure_generate(prompt=prompt, model=mdl, temperature=temperature, max_tokens=max_tokens)
        return text
