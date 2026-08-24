"""
AgentOS Phase 9 — Python SDK Tasks Client.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
import httpx

from agentos.exceptions import (
    AgentOSError,
    AuthenticationError,
    AuthorizationError,
    NotFoundError,
    RateLimitError,
    ServerError,
    ValidationError,
)
from agentos.models import (
    TaskCreateRequest,
    TaskEvent,
    TaskResponse,
    TaskResultResponse,
    TaskStatusResponse,
)


class TasksClient:
    """SDK client for interacting with AgentOS Tasks API."""

    def __init__(self, client: Any) -> None:
        self._client = client

    def create(
        self,
        task: str,
        priority: int = 1,
        requested_agent: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
        execution_mode: str = "autonomous",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> TaskResponse:
        """Submit a new task to AgentOS platform."""
        payload = {
            "task": task,
            "priority": priority,
            "requested_agent": requested_agent,
            "context": context or {},
            "execution_mode": execution_mode,
            "metadata": metadata or {},
        }
        res = self._client._request("POST", "/api/v1/tasks", json=payload)
        return TaskResponse(**res)

    def get(self, task_id: str) -> TaskResponse:
        """Fetch details of a task by ID."""
        res = self._client._request("GET", f"/api/v1/tasks/{task_id}")
        return TaskResponse(**res)

    def list(self, limit: int = 20, offset: int = 0) -> List[TaskResponse]:
        """List tasks with pagination."""
        res = self._client._request("GET", "/api/v1/tasks", params={"limit": limit, "offset": offset})
        return [TaskResponse(**t) for t in res]

    def status(self, task_id: str) -> TaskStatusResponse:
        """Get live execution lifecycle status of a task."""
        res = self._client._request("GET", f"/api/v1/tasks/{task_id}/status")
        return TaskStatusResponse(**res)

    def result(self, task_id: str) -> TaskResultResponse:
        """Get final completed result summary of a task."""
        res = self._client._request("GET", f"/api/v1/tasks/{task_id}/result")
        return TaskResultResponse(**res)

    def events(self, task_id: str, limit: int = 100) -> List[TaskEvent]:
        """Get chronological execution events for a task."""
        res = self._client._request("GET", f"/api/v1/tasks/{task_id}/events", params={"limit": limit})
        return [TaskEvent(**e) for e in res]

    def cancel(self, task_id: str) -> Dict[str, Any]:
        """Cancel an in-flight or queued task."""
        return self._client._request("POST", f"/api/v1/tasks/{task_id}/cancel")
