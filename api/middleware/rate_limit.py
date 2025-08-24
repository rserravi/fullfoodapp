from __future__ import annotations
import time
from collections import deque, defaultdict
from typing import Deque, Dict, Optional, Set, Tuple, Callable
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from ..config import settings

class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Límite sliding-window por API key/user_id (en memoria).
    Desarrollado para despliegue simple (1 proceso). En multi-proceso usar Redis.
    """
    def __init__(self, app):
        super().__init__(app)
        self.window_s = 60.0
        self.limit = settings.rate_limit_rpm
        self.burst = settings.rate_limit_burst
        self.exempt: Set[str] = {"/health", "/metrics", "/docs", "/openapi.json"}
        self.buckets: Dict[str, Deque[float]] = defaultdict(deque)

    def _identity(self, request: Request) -> str:
        # Igual que security.get_current_user, pero sin validar: sólo queremos una clave estable
        token = request.headers.get("X-API-Key")
        if not token:
            auth = request.headers.get("Authorization", "")
            if auth.lower().startswith("bearer "):
                token = auth.split(" ", 1)[1]
        if token:
            # mapear token->user_id para que varios tokens no compartan bucket accidentalmente
            token_to_user = settings.parsed_api_keys()
            return token_to_user.get(token, "unknown")
        # fallback dev
        return settings.auth_fallback_user or "anonymous"

    async def dispatch(self, request: Request, call_next):
        if request.url.path in self.exempt or request.method == "OPTIONS":
            return await call_next(request)

        key = self._identity(request)
        now = time.monotonic()
        q = self.buckets[key]

        # limpia fuera de ventana
        while q and (now - q[0]) > self.window_s:
            q.popleft()

        # aplica burst y límite
        if len(q) >= max(self.limit, self.burst):
            return JSONResponse({"detail": "Rate limit exceeded"}, status_code=429)

        q.append(now)
        return await call_next(request)
