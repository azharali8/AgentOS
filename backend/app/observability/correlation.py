"""
AgentOS Phase 6 — Correlation Middleware.

FastAPI middleware that generates/extracts request_id and correlation_id headers
and populates the ContextVar tracking context.
"""

from __future__ import annotations

import uuid
from typing import Callable
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from backend.app.observability.context import clear_correlation_context, set_correlation_context


class CorrelationMiddleware(BaseHTTPMiddleware):
    """Intercepts requests to set up and propagate correlation IDs."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        req_id = request.headers.get("X-Request-ID") or f"req-{uuid.uuid4().hex[:8]}"
        corr_id = request.headers.get("X-Correlation-ID") or f"corr-{uuid.uuid4().hex[:8]}"

        set_correlation_context(request_id=req_id, correlation_id=corr_id)
        try:
            response: Response = await call_next(request)
            response.headers["X-Request-ID"] = req_id
            response.headers["X-Correlation-ID"] = corr_id
            return response
        finally:
            clear_correlation_context()
