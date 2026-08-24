"""
AgentOS Phase 9 — Python SDK Main Client.
"""

from __future__ import annotations

from typing import Any, Dict, Optional
import httpx

from agentos.exceptions import (
    AgentOSError,
    AuthenticationError,
    AuthorizationError,
    NotFoundError,
    RateLimitError,
    ServerError,
    TimeoutError,
    ValidationError,
)
from agentos.tasks import TasksClient
from agentos.agents import AgentsClient
from agentos.system import SystemClient


class AgentOS:
    """
    Official AgentOS Python SDK Client.

    Example usage:
        from agentos import AgentOS

        client = AgentOS(base_url="http://localhost:8000", api_key="secret-key")
        task = client.tasks.create("Profile and clean dataset.csv")
        status = client.tasks.status(task.task_id)
    """

    def __init__(
        self,
        base_url: str = "http://localhost:8000",
        api_key: Optional[str] = None,
        timeout: float = 30.0,
        transport: Optional[httpx.BaseTransport] = None,
        app: Optional[Any] = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout
        
        # Support in-process ASGI app testing via TestClient
        if app is not None:
            from fastapi.testclient import TestClient
            self._http_client = TestClient(app=app, base_url=self.base_url)
        elif transport is not None:
            self._http_client = httpx.Client(transport=transport, base_url=self.base_url, timeout=timeout)
        else:
            self._http_client = httpx.Client(base_url=self.base_url, timeout=timeout)

        # Sub-clients
        self.tasks = TasksClient(self)
        self.agents = AgentsClient(self)
        self.system = SystemClient(self)

    def _request(
        self,
        method: str,
        path: str,
        params: Optional[Dict[str, Any]] = None,
        json: Optional[Dict[str, Any]] = None,
    ) -> Any:
        headers = {}
        if self.api_key:
            headers["X-API-Key"] = self.api_key

        try:
            resp = self._http_client.request(
                method=method,
                url=path,
                params=params,
                json=json,
                headers=headers,
            )
        except httpx.TimeoutException as exc:
            raise TimeoutError(f"Request to {path} timed out: {exc}") from exc
        except httpx.RequestError as exc:
            raise AgentOSError(f"Network error communicating with AgentOS: {exc}") from exc

        if resp.is_success:
            if resp.status_code == 204 or not resp.content:
                return {}
            return resp.json()

        # Handle structured error codes
        status = resp.status_code
        err_detail = resp.text
        try:
            data = resp.json()
            if isinstance(data, dict):
                err_detail = data.get("detail", err_detail)
        except Exception:
            pass

        if status == 401:
            raise AuthenticationError(f"Authentication failed: {err_detail}", status_code=status)
        elif status == 403:
            raise AuthorizationError(f"Permission denied: {err_detail}", status_code=status)
        elif status == 404:
            raise NotFoundError(f"Resource not found: {err_detail}", status_code=status)
        elif status == 422:
            raise ValidationError(f"Validation error: {err_detail}", status_code=status)
        elif status == 429:
            raise RateLimitError(f"Rate limit exceeded: {err_detail}", status_code=status)
        elif status >= 500:
            raise ServerError(f"AgentOS internal error ({status}): {err_detail}", status_code=status)
        else:
            raise AgentOSError(f"HTTP error {status}: {err_detail}", status_code=status)

    def close(self) -> None:
        self._http_client.close()

    def __enter__(self) -> AgentOS:
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()
