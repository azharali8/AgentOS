"""
AgentOS Phase 16 — Central Redis Client Management.
Provides connection pooling, health checks, and unified client access.
"""


from __future__ import annotations

import logging
from typing import Optional
import redis

from backend.app.config.settings import settings

logger = logging.getLogger("agentos.redis")

_redis_pool: Optional[redis.ConnectionPool] = None
_redis_client: Optional[redis.Redis] = None


class RedisUnavailableError(Exception):
    """Raised when Redis operations are requested but Redis is unreachable."""
    pass


def get_redis_pool() -> redis.ConnectionPool:
    """Obtain or initialize the shared thread-safe Redis connection pool."""
    global _redis_pool
    if _redis_pool is None:
        _redis_pool = redis.ConnectionPool.from_url(
            settings.REDIS_URL,
            max_connections=settings.REDIS_MAX_CONNECTIONS,
            socket_timeout=settings.REDIS_SOCKET_TIMEOUT,
            socket_connect_timeout=settings.REDIS_SOCKET_TIMEOUT,
            decode_responses=True,
        )
    return _redis_pool


def get_redis_client() -> redis.Redis:
    """Return a thread-safe Redis client instance backed by connection pool."""
    global _redis_client
    if _redis_client is None:
        pool = get_redis_pool()
        _redis_client = redis.Redis(connection_pool=pool)
    return _redis_client


_last_redis_check: float = 0.0
_redis_available_cached: bool = False
_CHECK_INTERVAL: float = 5.0


def is_redis_available() -> bool:
    """Check if Redis is reachable via active ping with cached result."""
    global _last_redis_check, _redis_available_cached
    import time
    now = time.time()
    if now - _last_redis_check < _CHECK_INTERVAL:
        return _redis_available_cached

    _last_redis_check = now
    try:
        client = get_redis_client()
        _redis_available_cached = bool(client.ping())
        return _redis_available_cached
    except Exception:
        _redis_available_cached = False
        return False


def reset_redis_client_for_test() -> None:
    """Reset the global client and pool (test/benchmark use only)."""
    global _redis_pool, _redis_client, _last_redis_check, _redis_available_cached
    _last_redis_check = 0.0
    _redis_available_cached = False
    if _redis_client:
        try:
            _redis_client.close()
        except Exception:
            pass
    _redis_pool = None
    _redis_client = None
