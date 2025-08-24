from __future__ import annotations
from typing import Optional
from fastapi import Header, HTTPException
from .config import settings

def _extract_token(x_api_key: Optional[str], authorization: Optional[str]) -> Optional[str]:
    """
    Devuelve el token de la cabecera X-API-Key o de Authorization: Bearer <token>.
    """
    if x_api_key:
        tok = x_api_key.strip()
        if tok:
            return tok
    if authorization:
        parts = authorization.split(" ", 1)
        if len(parts) == 2 and parts[0].lower() == "bearer":
            tok = parts[1].strip()
            if tok:
                return tok
    return None

def get_current_user(
    x_api_key: Optional[str] = Header(default=None, alias="X-API-Key"),
    authorization: Optional[str] = Header(default=None, alias="Authorization"),
) -> str:
    """
    Dependencia FastAPI que resuelve el user_id a partir del token.
    - Si hay token y existe en API_KEYS -> devuelve su user_id.
    - Si hay token pero no existe -> 401.
    - Si no hay token:
        - Si AUTH_FALLBACK_USER está configurado -> usa ese user_id (modo dev).
        - Si no -> 401.
    """
    token = _extract_token(x_api_key, authorization)
    mapping = settings.parsed_api_keys()  # {token -> user_id}

    if token:
        user_id = mapping.get(token)
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid API key")
        return user_id

    # Sin token
    if settings.auth_fallback_user:
        return settings.auth_fallback_user

    raise HTTPException(status_code=401, detail="Missing API key")
