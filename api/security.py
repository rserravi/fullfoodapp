from __future__ import annotations
from typing import Optional, Dict, Any
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Header, HTTPException

from .config import settings

ALGO = "HS256"

def create_access_token(user_id: str, expires_minutes: int | None = None) -> str:
    exp_minutes = expires_minutes or 60
    now = datetime.now(tz=timezone.utc)
    payload: Dict[str, Any] = {
        "sub": user_id,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=exp_minutes)).timestamp()),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=ALGO)

def _decode_jwt(token: str) -> str:
    try:
        data = jwt.decode(token, settings.jwt_secret, algorithms=[ALGO])
        sub = data.get("sub")
        if not sub or not isinstance(sub, str):
            raise HTTPException(status_code=401, detail="Invalid token payload")
        return sub
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")

def _extract_token(x_api_key: Optional[str], authorization: Optional[str]) -> tuple[Optional[str], Optional[str]]:
    """
    Devuelve (api_key, bearer_token)
    """
    api_key = x_api_key.strip() if x_api_key else None
    bearer = None
    if authorization:
        parts = authorization.split(" ", 1)
        if len(parts) == 2 and parts[0].lower() == "bearer":
            bearer = parts[1].strip()
    return api_key or None, bearer or None

def get_current_user(
    x_api_key: Optional[str] = Header(default=None, alias="X-API-Key"),
    authorization: Optional[str] = Header(default=None, alias="Authorization"),
) -> str:
    api_key, bearer = _extract_token(x_api_key, authorization)
    # 1) JWT Bearer
    if bearer:
        return _decode_jwt(bearer)

    # 2) API Key (dev / backend-to-backend)
    if api_key:
        mapping = settings.parsed_api_keys()  # token -> user_id
        user_id = mapping.get(api_key)
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid API key")
        return user_id

    # 3) Fallback dev (si está configurado)
    if settings.auth_fallback_user:
        return settings.auth_fallback_user

    raise HTTPException(status_code=401, detail="Missing credentials")
