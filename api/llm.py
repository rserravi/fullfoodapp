import httpx
from typing import Optional, Dict, Any
from .config import settings

async def generate_json(prompt: str, model: Optional[str] = None, temperature: float = 0.2, max_tokens: int = 1024) -> str:
    mdl = model or settings.llm_model
    payload: Dict[str, Any] = {"model": mdl, "prompt": prompt, "stream": False, "format": "json", "options": {"temperature": temperature}}
    async with httpx.AsyncClient(timeout=180) as client:
        r = await client.post(settings.ollama_url + "/api/generate", json=payload)
        r.raise_for_status()
        data = r.json()
        return data.get("response", "").strip()
