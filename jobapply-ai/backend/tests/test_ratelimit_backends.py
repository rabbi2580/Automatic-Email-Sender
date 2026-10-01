"""Rate limiter backends and client-IP trust. The Redis test is skipped when no local Redis is reachable."""
import time

import pytest
from starlette.requests import Request

from app.core import ratelimit
from app.core.config import get_settings


def _req(xff=None, host="9.9.9.9"):
    headers = [(b"x-forwarded-for", xff.encode())] if xff else []
    return Request({"type": "http", "headers": headers, "client": (host, 1), "method": "GET", "path": "/"})


def test_xff_ignored_by_default():
    assert ratelimit.client_ip(_req("1.2.3.4")) == "9.9.9.9"


def test_xff_trusted_hops(monkeypatch):
    monkeypatch.setattr(get_settings(), "trusted_proxy_hops", 1)
    # client forged the first entry; our single proxy appended the real address last
    assert ratelimit.client_ip(_req("6.6.6.6, 5.5.5.5")) == "5.5.5.5"


def test_memory_limiter_window():
    lim = ratelimit._MemoryLimiter()
    assert all(lim.hit("k", 3, 60)[0] for _ in range(3))
    ok, retry = lim.hit("k", 3, 60)
    assert not ok and retry >= 1
    lim.clear("k")
    assert lim.hit("k", 3, 60)[0]


def test_redis_limiter_shared_state():
    try:
        lim = ratelimit._RedisLimiter(get_settings().redis_url)
        lim.r.ping()
    except Exception:  # noqa: BLE001
        pytest.skip("no redis available")
    key = f"t{time.time_ns()}"
    other = ratelimit._RedisLimiter(get_settings().redis_url)  # a second "process"
    assert lim.hit(key, 2, 30)[0] and other.hit(key, 2, 30)[0]
    assert not lim.hit(key, 2, 30)[0]
    assert lim.exceeded(key, 2, 30)[0]
    other.clear(key)
    assert lim.hit(key, 2, 30)[0]
