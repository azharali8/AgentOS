"""
AgentOS Phase 6 & 14 — Tiered Multi-Domain Rate Limiter.

Provides independent windowed rate limit tracking for:
- Authentication (/api/v1/auth/*) -> 5 req/min
- Task creation (POST /api/v1/tasks) -> 10 req/min
- Standard API endpoints -> 100 req/min
- WebSocket connections -> 5 conns/min
"""

from __future__ import annotations

import time
from collections import defaultdict
from typing import Dict, List
from fastapi import HTTPException, status

from backend.app.config.settings import settings


class RateLimiter:
    """Multi-domain sliding-window in-memory rate limiter."""

    _request_windows: Dict[str, List[float]] = defaultdict(list)
    _domain_limits: Dict[str, int] = {
        "auth": 5,
        "task_create": 10,
        "api": 100,
        "ws": 5,
    }

    @classmethod
    def _check_redis_rate_limit(
        cls,
        key: str,
        domain: str,
        domain_limit: int,
        window_seconds: int = 60,
    ) -> bool:
        """Atomic sliding window rate limit check via Redis Sorted Set."""
        from backend.app.services.redis_client import get_redis_client, is_redis_available
        if not is_redis_available():
            # Graceful fallback to in-memory check
            return cls._check_memory_rate_limit(key, domain, domain_limit, window_seconds)

        client = get_redis_client()
        now = time.time()
        bucket_key = f"agentos:rl:{domain}:{key}"
        window_start = now - window_seconds

        # Redis Lua script for atomic sliding window evaluation
        LUA_RATE_LIMIT = """
        local key = KEYS[1]
        local now = tonumber(ARGV[1])
        local window_start = tonumber(ARGV[2])
        local limit = tonumber(ARGV[3])
        local ttl = tonumber(ARGV[4])

        redis.call("ZREMRANGEBYSCORE", key, "-inf", window_start)
        local count = redis.call("ZCARD", key)

        if count >= limit then
            return 0
        else
            redis.call("ZADD", key, now, tostring(now) .. "-" .. tostring(math.random(100000)))
            redis.call("EXPIRE", key, ttl)
            return 1
        end
        """
        try:
            res = client.eval(LUA_RATE_LIMIT, 1, bucket_key, str(now), str(window_start), str(domain_limit), str(window_seconds + 5))
            if res == 0:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail={
                        "error": {
                            "code": "RATE_LIMIT_EXCEEDED",
                            "message": f"Rate limit exceeded for domain '{domain}'. Max {domain_limit} requests per {window_seconds}s.",
                        }
                    },
                )
            return True
        except HTTPException:
            raise
        except Exception:
            # On unexpected Redis failure, fallback to in-memory
            return cls._check_memory_rate_limit(key, domain, domain_limit, window_seconds)

    @classmethod
    def _check_memory_rate_limit(
        cls,
        key: str,
        domain: str,
        domain_limit: int,
        window_seconds: int = 60,
    ) -> bool:
        now = time.time()
        bucket_key = f"{domain}:{key}"

        # Clean old timestamps
        cls._request_windows[bucket_key] = [
            ts for ts in cls._request_windows[bucket_key] if now - ts < window_seconds
        ]

        if len(cls._request_windows[bucket_key]) >= domain_limit:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail={
                    "error": {
                        "code": "RATE_LIMIT_EXCEEDED",
                        "message": f"Rate limit exceeded for domain '{domain}'. Max {domain_limit} requests per {window_seconds}s.",
                    }
                },
            )

        cls._request_windows[bucket_key].append(now)
        return True

    @classmethod
    def check_rate_limit(cls, key: str, domain: str = "api", limit: int | None = None, window_seconds: int = 60) -> bool:
        """
        Check rate limit under sliding window.
        Uses Redis or in-memory backend based on RATE_LIMIT_BACKEND setting.
        Raises HTTPException(429) if exceeded.
        """
        domain_limit = limit or cls._domain_limits.get(domain, settings.RATE_LIMIT_REQUESTS)
        backend = getattr(settings, "RATE_LIMIT_BACKEND", "memory")

        if backend == "redis":
            return cls._check_redis_rate_limit(key, domain, domain_limit, window_seconds)
        return cls._check_memory_rate_limit(key, domain, domain_limit, window_seconds)

    @classmethod
    def reset(cls) -> None:
        cls._request_windows.clear()
        try:
            from backend.app.services.redis_client import get_redis_client, is_redis_available
            if is_redis_available():
                client = get_redis_client()
                for key in client.scan_iter("agentos:rl:*"):
                    client.delete(key)
        except Exception:
            pass

    @classmethod
    def reset_for_test(cls, key: str, domain: str) -> None:
        """Clear the rate-limit bucket for a specific key+domain (test/benchmark use only)."""
        bucket_key = f"{domain}:{key}"
        cls._request_windows.pop(bucket_key, None)
        try:
            from backend.app.services.redis_client import get_redis_client, is_redis_available
            if is_redis_available():
                client = get_redis_client()
                client.delete(f"agentos:rl:{domain}:{key}")
        except Exception:
            pass


# Backward-compatibility alias used by existing test files
RequestGuard = RateLimiter



