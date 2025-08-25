# api/services/cache.py
from __future__ import annotations

from typing import Any, Optional, Dict
from datetime import datetime, timedelta, timezone
import hashlib
import json

from sqlmodel import Session, select
from ..models_db import Cache


# ---------------------------
# Helpers de tiempo (UTC aware)
# ---------------------------

def now_utc() -> datetime:
    """Fecha/hora actual en UTC con tzinfo (aware)."""
    return datetime.now(timezone.utc)


def _as_aware(dt: Optional[datetime]) -> Optional[datetime]:
    """Convierte un datetime a UTC-aware. Si viene naive, asumimos UTC."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


# ---------------------------
# Claves y serialización
# ---------------------------

def make_key(prefix: str, parts: Dict[str, Any]) -> str:
    """
    Crea una clave determinista y corta a partir de un dict.
    """
    raw = json.dumps(parts, sort_keys=True, ensure_ascii=False)
    h = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]
    return f"{prefix}:{h}"


# ---------------------------
# Acceso a caché
# ---------------------------

def get_cache(session: Session, user_id: str, key: str) -> Optional[Cache]:
    """
    Devuelve la fila de caché válida o None. Si está expirada, la borra.
    """
    row = session.exec(
        select(Cache).where(Cache.user_id == user_id, Cache.key == key)
    ).first()

    if not row:
        return None

    expires_at = _as_aware(row.expires_at)
    if expires_at and expires_at < now_utc():
        # expirada → eliminar
        session.delete(row)
        session.commit()
        return None

    return row


def set_cache(
    session: Session,
    user_id: str,
    key: str,
    payload: Any,
    ttl_seconds: int = 3600,
) -> None:
    """
    Upsert de una entrada en caché. Siempre guarda fechas aware (UTC).
    """
    expires_at = now_utc() + timedelta(seconds=ttl_seconds)
    row = session.exec(
        select(Cache).where(Cache.user_id == user_id, Cache.key == key)
    ).first()

    if row:
        row.payload = payload
        row.expires_at = _as_aware(expires_at)
        row.updated_at = now_utc()
        session.add(row)
    else:
        row = Cache(
            user_id=user_id,
            key=key,
            payload=payload,
            created_at=now_utc(),
            updated_at=now_utc(),
            expires_at=_as_aware(expires_at),
        )
        session.add(row)

    session.commit()


def get_payload(session: Session, user_id: str, key: str) -> Optional[Any]:
    """
    Devuelve solo el payload (o None si no existe / está expirado).
    """
    row = get_cache(session, user_id, key)
    return row.payload if row else None


def set_payload(
    session: Session,
    user_id: str,
    key: str,
    payload: Any,
    ttl_seconds: int = 3600,
) -> None:
    set_cache(session, user_id, key, payload, ttl_seconds)
