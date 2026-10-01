"""Sliding-window rate limiter. `RATE_LIMIT_BACKEND=memory` (default; per process) or `redis` (shared across API workers/replicas)."""
from __future__ import annotations

import threading
import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request

from app.core.config import get_settings


class _MemoryLimiter:
    def __init__(self) -> None:
        self.hits: dict[str, deque[float]] = defaultdict(deque)
        self.lock = threading.Lock()

    def hit(self, key: str, limit: int, window: int) -> tuple[bool, int]:
        now = time.monotonic()
        with self.lock:
            q = self.hits[key]
            while q and q[0] <= now - window:
                q.popleft()
            if len(q) >= limit:
                return False, max(1, int(window - (now - q[0])))
            q.append(now)
            return True, 0

    def exceeded(self, key: str, limit: int, window: int) -> tuple[bool, int]:
        """Check without recording a hit."""
        now = time.monotonic()
        with self.lock:
            q = self.hits.get(key)
            if not q:
                return False, 0
            while q and q[0] <= now - window:
                q.popleft()
            return (len(q) >= limit, max(1, int(window - (now - q[0]))) if q else 0)

    def clear(self, key: str) -> None:
        with self.lock:
            self.hits.pop(key, None)

    def reset(self) -> None:
        with self.lock:
            self.hits.clear()


class _RedisLimiter:
    """Sliding window on a sorted set. If Redis is unreachable we fail open on the shared limiter (availability) but keep the in-process limiter as a floor."""

    def __init__(self, url: str) -> None:
        import redis

        self.r = redis.Redis.from_url(url, socket_timeout=0.5, socket_connect_timeout=0.5)
        self.fallback = _MemoryLimiter()

    def _k(self, key: str) -> str:
        return f"rl:{key}"

    def hit(self, key: str, limit: int, window: int) -> tuple[bool, int]:
        try:
            now = time.time()
            k = self._k(key)
            pipe = self.r.pipeline()
            pipe.zremrangebyscore(k, 0, now - window)
            pipe.zcard(k)
            pipe.zrange(k, 0, 0, withscores=True)
            _, n, oldest = pipe.execute()
            if n >= limit:
                return False, max(1, int(window - (now - oldest[0][1]))) if oldest else 1
            pipe = self.r.pipeline()
            pipe.zadd(k, {f"{now}:{time.monotonic_ns()}": now})
            pipe.expire(k, window + 5)
            pipe.execute()
            return True, 0
        except Exception:  # noqa: BLE001
            return self.fallback.hit(key, limit, window)

    def exceeded(self, key: str, limit: int, window: int) -> tuple[bool, int]:
        try:
            now = time.time()
            k = self._k(key)
            self.r.zremrangebyscore(k, 0, now - window)
            n = self.r.zcard(k)
            if n < limit:
                return False, 0
            oldest = self.r.zrange(k, 0, 0, withscores=True)
            return True, max(1, int(window - (now - oldest[0][1]))) if oldest else 1
        except Exception:  # noqa: BLE001
            return self.fallback.exceeded(key, limit, window)

    def clear(self, key: str) -> None:
        self.fallback.clear(key)
        try:
            self.r.delete(self._k(key))
        except Exception:  # noqa: BLE001
            pass

    def reset(self) -> None:
        self.fallback.reset()
        try:
            for k in self.r.scan_iter("rl:*"):
                self.r.delete(k)
        except Exception:  # noqa: BLE001
            pass


def _make_limiter():
    s = get_settings()
    if s.rate_limit_backend == "redis":
        return _RedisLimiter(s.redis_url)
    return _MemoryLimiter()


limiter = _make_limiter()


def client_ip(request: Request) -> str:
    """X-Forwarded-For is client-controlled, so it is honoured only when TRUSTED_PROXY_HOPS > 0 (number of proxies you operate in front of the API);
    the address appended by the outermost trusted proxy is then used."""
    hops = get_settings().trusted_proxy_hops
    fwd = request.headers.get("x-forwarded-for")
    if hops > 0 and fwd:
        parts = [p.strip() for p in fwd.split(",") if p.strip()]
        if parts:
            return parts[-min(hops, len(parts))]
    return request.client.host if request.client else "unknown"


def rate_limit(name: str, per_minute: int | None = None, per_user: bool = False):
    """FastAPI dependency factory."""

    def dep(request: Request) -> None:
        s = get_settings()
        if s.environment == "test" and not getattr(request.app.state, "enforce_rate_limits", False):
            return
        limit = per_minute or s.rate_limit_per_minute
        who = getattr(request.state, "user_id", None) if per_user else None
        key = f"{name}:{who or client_ip(request)}"
        ok, retry = limiter.hit(key, limit, 60)
        if not ok:
            raise HTTPException(429, detail={"code": "rate_limited", "message": "Too many requests. Please slow down."}, headers={"Retry-After": str(retry)})

    return dep
