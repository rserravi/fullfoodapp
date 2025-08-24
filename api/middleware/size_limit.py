from __future__ import annotations
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from ..errors import ErrorResponse
from ..config import settings

class SizeLimitMiddleware(BaseHTTPMiddleware):
    """
    Rechaza peticiones cuyo Content-Length excede MAX_BODY_BYTES.
    Si no hay Content-Length, permite (evitamos leer el body en middleware).
    """
    def __init__(self, app):
        super().__init__(app)
        self.max_bytes = settings.max_body_bytes

    async def dispatch(self, request: Request, call_next):
        cl = request.headers.get("content-length")
        if cl:
            try:
                size = int(cl)
                if size > self.max_bytes:
                    err = ErrorResponse(code="payload_too_large", detail=f"Body too large (> {self.max_bytes} bytes)", meta={"max": self.max_bytes})
                    return JSONResponse(status_code=413, content=err.model_dump())
            except Exception:
                pass
        return await call_next(request)
