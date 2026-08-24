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
    def check_rate_limit(cls, key: str, domain: str = "api", limit: int | None = None, window_seconds: int = 60) -> bool:
        """
        Check rate limit under sliding window.
        Raises HTTPException(429) if exceeded.
        """
        domain_limit = limit or cls._domain_limits.get(domain, settings.RATE_LIMIT_REQUESTS)
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
                }
            )

        cls._request_windows[bucket_key].append(now)
        return True

    @classmethod
    def reset(cls) -> None:
        cls._request_windows.clear()

    @classmethod
    def reset_for_test(cls, key: str, domain: str) -> None:
        """Clear the rate-limit bucket for a specific key+domain (test/benchmark use only)."""
        bucket_key = f"{domain}:{key}"
        cls._request_windows.pop(bucket_key, None)


# Backward-compatibility alias used by existing test files
RequestGuard = RateLimiter


