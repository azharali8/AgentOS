"""
AgentOS Phase 6 — Sliding-Window Rate Limiter & Request Guard.

Protects API endpoints against:
- High-frequency brute force / abuse
- Oversized payload attacks
- Malformed JSON recursion depth attacks
"""

from __future__ import annotations

import time
from collections import defaultdict, deque
from typing import Dict, Optional
from fastapi import HTTPException, Request, status

from backend.app.config.settings import settings


class RateLimiter:
    """Sliding-window rate limiter keyed by client IP or API key."""

    # key -> deque of timestamp floats
    _requests: Dict[str, deque[float]] = defaultdict(deque)

    @classmethod
    def check_rate_limit(
        cls,
        key: str,
        limit: Optional[int] = None,
        window_seconds: Optional[int] = None,
    ) -> None:
        """Enforce rate limits. Raises HTTPException(429) if exceeded."""
        max_reqs = limit or settings.RATE_LIMIT_REQUESTS
        window = window_seconds or settings.RATE_LIMIT_WINDOW

        now = time.time()
        q = cls._requests[key]

        # Purge timestamps outside sliding window
        while q and q[0] <= now - window:
            q.popleft()

        if len(q) >= max_reqs:
            retry_after = int(window - (now - q[0])) + 1
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Rate limit exceeded. Please retry later.",
                headers={"Retry-After": str(max(1, retry_after))},
            )

        q.append(now)

    @classmethod
    def reset(cls) -> None:
        cls._requests.clear()


class RequestGuard:
    """Validates request size and JSON nesting structure."""

    @staticmethod
    def validate_content_length(content_length: Optional[int]) -> None:
        """Reject requests exceeding MAX_REQUEST_BODY_SIZE."""
        max_bytes = settings.MAX_REQUEST_BODY_SIZE
        if content_length and content_length > max_bytes:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"Request body exceeds maximum allowed size of {max_bytes} bytes.",
            )

    @staticmethod
    def validate_json_depth(obj: Any, current_depth: int = 0) -> None:
        """Check recursion depth of nested JSON structures."""
        max_depth = settings.MAX_JSON_DEPTH
        if current_depth > max_depth:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"JSON nesting depth exceeds maximum limit of {max_depth}.",
            )
        if isinstance(obj, dict):
            for v in obj.values():
                RequestGuard.validate_json_depth(v, current_depth + 1)
        elif isinstance(obj, list):
            for item in obj:
                RequestGuard.validate_json_depth(item, current_depth + 1)
