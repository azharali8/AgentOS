"""
AgentOS Phase 6 — Correlation and Execution Context.

Maintains ContextVar-based tracking for:
- request_id
- task_id
- agent_id
- correlation_id
"""

from __future__ import annotations

import contextvars
import uuid
from typing import Optional

_request_id_ctx: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar("request_id", default=None)
_task_id_ctx: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar("task_id", default=None)
_agent_id_ctx: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar("agent_id", default=None)
_correlation_id_ctx: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar("correlation_id", default=None)


def set_correlation_context(
    request_id: Optional[str] = None,
    task_id: Optional[str] = None,
    agent_id: Optional[str] = None,
    correlation_id: Optional[str] = None,
) -> None:
    """Set correlation variables for the current thread/async task."""
    _request_id_ctx.set(request_id or f"req-{uuid.uuid4().hex[:8]}")
    if task_id:
        _task_id_ctx.set(task_id)
    if agent_id:
        _agent_id_ctx.set(agent_id)
    _correlation_id_ctx.set(correlation_id or f"corr-{uuid.uuid4().hex[:8]}")


def get_correlation_context() -> dict[str, Optional[str]]:
    """Retrieve current correlation context dictionary."""
    return {
        "request_id": _request_id_ctx.get(),
        "task_id": _task_id_ctx.get(),
        "agent_id": _agent_id_ctx.get(),
        "correlation_id": _correlation_id_ctx.get(),
    }


def clear_correlation_context() -> None:
    """Reset context variables."""
    _request_id_ctx.set(None)
    _task_id_ctx.set(None)
    _agent_id_ctx.set(None)
    _correlation_id_ctx.set(None)
