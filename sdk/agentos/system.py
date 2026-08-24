"""
AgentOS Phase 9 — Python SDK System Client.
"""

from __future__ import annotations

from typing import Any, Dict
from agentos.models import SystemHealthResponse, SystemReadinessResponse


class SystemClient:
    """SDK client for platform health, readiness, and metrics."""

    def __init__(self, client: Any) -> None:
        self._client = client

    def health(self) -> SystemHealthResponse:
        """Fetch platform liveness probe."""
        res = self._client._request("GET", "/api/v1/system/health")
        return SystemHealthResponse(**res)

    def readiness(self) -> SystemReadinessResponse:
        """Fetch production subsystem readiness probe."""
        res = self._client._request("GET", "/api/v1/system/readiness")
        return SystemReadinessResponse(**res)

    def version(self) -> Dict[str, Any]:
        """Fetch platform and API version metadata."""
        return self._client._request("GET", "/api/v1/system/version")

    def metrics(self) -> Dict[str, Any]:
        """Fetch live system and LLM usage metrics."""
        return self._client._request("GET", "/api/v1/system/metrics")
