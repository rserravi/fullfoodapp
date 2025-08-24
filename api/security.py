from typing import Optional
from fastapi import Header, HTTPException, status
from .config import settings

def get_current_user(
    x_api_key: Optional[str] = Header(default=None, alias="X-API-Key"),
    authorization: Optional[str] = Header(default=None, alias="Authorization"),
) -> str:
    """
    Resuelve el user_id a partir de:
    - X-API-Key: <token>
    - Authorization: Bearer <token>
    Si no hay token y hay 'auth_fallback_user' configurado, devuelve ese usuario.
    """
    token_to_user = settings.parsed_api_keys()

    token: Optional[str] = None
    if x_api_key:
        token = x_api_key.strip()
    elif authorization and authorization.lower().startswith("bearer "):
        token = authorization.split(" ", 1)[1].strip()

    if token:
        user = token_to_user.get(token)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="API key inválida",
            )
        return user

    # Fallback para desarrollo local
    if settings.auth_fallback_user:
        return settings.auth_fallback_user

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Falta API key",
    )
