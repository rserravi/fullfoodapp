from __future__ import annotations
from typing import Optional, Any, Dict
from datetime import datetime, timezone, timedelta
import json
import hashlib
from prometheus_client import Counter
from sqlmodel import Session, select
from ..models_db import KVCache

CACHE_HIT = Counter("cache_hit_total", "Cache hits", ["key_prefix"])
CACHE_MISS = Counter("cache_miss_total", "Cache misses", ["key_prefix"])

def now_utc() -> datetime:
    return datetime.now(timezone.utc)

def make_key(prefix: str, payload: Dict[str, Any]) -> str:
    blob = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    h = hashlib.sha1(blob.encode("utf-8")).hexdigest()
    return f"{prefix}:{h}"

def _label_from_key(key: str) -> str:
    return key.split(":", 1)[0] if ":" in key else key

def get_cache(session: Session, user_id: str, key: str) -> Optional[Dict[str, Any]]:
    row = session.exec(
        select(KVCache).where(KVCache.user_id == user_id, KVCache.key == key).limit(1)
    ).first()
    if not row:
        CACHE_MISS.labels(_label_from_key(key)).inc()
        return None
    if row.expires_at and row.expires_at < now_utc():
        session.delete(row)
        session.commit()
        CACHE_MISS.labels(_label_from_key(key)).inc()
        return None
    CACHE_HIT.labels(_label_from_key(key)).inc()
    return row.value

def set_cache(session: Session, user_id: str, key: str, value: Dict[str, Any], ttl_seconds: Optional[int] = None):
    expires_at = None
    if ttl_seconds:
        expires_at = now_utc() + timedelta(seconds=ttl_seconds)
    old = session.exec(
        select(KVCache).where(KVCache.user_id == user_id, KVCache.key == key)
    ).first()
    if old:
        session.delete(old)
        session.commit()
    session.add(KVCache(user_id=user_id, key=key, value=value, expires_at=expires_at))
    session.commit()

def get_payload(session: Session, user_id: str, key: str) -> Optional[Any]:
    v = get_cache(session, user_id, key)
    if isinstance(v, dict) and "payload" in v:
        return v["payload"]
    return None

def set_payload(session: Session, user_id: str, key: str, payload: Any, ttl_seconds: Optional[int] = None):
    set_cache(session, user_id, key, {"payload": payload}, ttl_seconds=ttl_seconds)

def delete_key(session: Session, user_id: str, key: str) -> int:
    row = session.exec(
        select(KVCache).where(KVCache.user_id == user_id, KVCache.key == key)
    ).first()
    if not row:
        return 0
    session.delete(row)
    session.commit()
    return 1

def delete_prefix(session: Session, user_id: str, prefix: str) -> int:
    rows = session.exec(
        select(KVCache).where(KVCache.user_id == user_id)
    ).all()
    n = 0
    for r in rows:
        if r.key.startswith(prefix + ":"):
            session.delete(r); n += 1
    if n:
        session.commit()
    return n
