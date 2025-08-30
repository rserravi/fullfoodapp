from __future__ import annotations
from collections import defaultdict, deque
from typing import Deque, Dict, Optional

try:  # pragma: no cover - optional dependency
    from redis.asyncio import Redis  # type: ignore
except Exception:  # pragma: no cover
    Redis = None  # type: ignore

from .config import settings


class RateLimitStore:
    def __init__(self) -> None:
        self._redis: Optional[Redis] = None
        self._local: Dict[str, Deque[float]] = defaultdict(deque)

    def _use_redis(self) -> bool:
        return bool(getattr(settings, "redis_url", None) and Redis is not None)

    def _client(self) -> Redis:
        assert Redis is not None, "redis package no disponible"
        assert settings.redis_url, "redis_url no configurado"
        if self._redis is None:
            self._redis = Redis.from_url(settings.redis_url, password=settings.redis_password)
        return self._redis

    async def allow(self, key: str, now: float, window: float, limit: int) -> bool:
        if self._use_redis():
            try:
                client = self._client()
                rkey = f"rl:{key}"
                min_score = now - window
                pipe = client.pipeline()
                pipe.zremrangebyscore(rkey, 0, min_score)
                pipe.zcard(rkey)
                _, count = await pipe.execute()
                if count >= limit:
                    return False
                pipe = client.pipeline()
                pipe.zadd(rkey, {now: now})
                pipe.expire(rkey, int(window))
                await pipe.execute()
                return True
            except Exception:
                pass  # fallback a memoria local
        q = self._local[key]
        while q and (now - q[0]) > window:
            q.popleft()
        if len(q) >= limit:
            return False
        q.append(now)
        return True


store = RateLimitStore()
