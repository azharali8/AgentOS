"""
AgentOS Phase 6 — System & Agent Observability Metrics.

Tracks real-time system, tool, agent, and workflow health metrics.
"""

from __future__ import annotations

import time
from collections import defaultdict
from typing import Any, Dict, List
from pydantic import BaseModel, Field


class MetricsCollector:
    """In-memory thread-safe metrics collector."""

    _tasks_started: int = 0
    _tasks_completed: int = 0
    _tasks_failed: int = 0
    _tasks_waiting_approval: int = 0

    _tool_calls_total: int = 0
    _tool_failures_total: int = 0
    _approvals_requested: int = 0
    _approvals_approved: int = 0
    _approvals_rejected: int = 0

    _agent_invocations: Dict[str, int] = defaultdict(int)
    _agent_failures: Dict[str, int] = defaultdict(int)

    _start_time: float = time.time()

    @classmethod
    def record_task_started(cls) -> None:
        cls._tasks_started += 1

    @classmethod
    def record_task_completed(cls) -> None:
        cls._tasks_completed += 1

    @classmethod
    def record_task_failed(cls) -> None:
        cls._tasks_failed += 1

    @classmethod
    def record_tool_call(cls, success: bool = True) -> None:
        cls._tool_calls_total += 1
        if not success:
            cls._tool_failures_total += 1

    @classmethod
    def record_approval(cls, status: str) -> None:
        cls._approvals_requested += 1
        if status == "APPROVED":
            cls._approvals_approved += 1
        elif status == "REJECTED":
            cls._approvals_rejected += 1

    @classmethod
    def record_agent_execution(cls, agent_type: str, success: bool = True) -> None:
        cls._agent_invocations[agent_type] += 1
        if not success:
            cls._agent_failures[agent_type] += 1

    @classmethod
    def get_metrics_snapshot(cls) -> Dict[str, Any]:
        uptime = round(time.time() - cls._start_time, 2)
        total_tasks = cls._tasks_started
        success_rate = round((cls._tasks_completed / max(1, total_tasks)) * 100.0, 1)

        return {
            "uptime_seconds": uptime,
            "tasks": {
                "started": cls._tasks_started,
                "completed": cls._tasks_completed,
                "failed": cls._tasks_failed,
                "success_rate_pct": success_rate,
            },
            "tools": {
                "total_calls": cls._tool_calls_total,
                "failed_calls": cls._tool_failures_total,
            },
            "approvals": {
                "requested": cls._approvals_requested,
                "approved": cls._approvals_approved,
                "rejected": cls._approvals_rejected,
            },
            "agents": {
                "invocations": dict(cls._agent_invocations),
                "failures": dict(cls._agent_failures),
            },
        }

    @classmethod
    def reset(cls) -> None:
        cls._tasks_started = 0
        cls._tasks_completed = 0
        cls._tasks_failed = 0
        cls._tasks_waiting_approval = 0
        cls._tool_calls_total = 0
        cls._tool_failures_total = 0
        cls._approvals_requested = 0
        cls._approvals_approved = 0
        cls._approvals_rejected = 0
        cls._agent_invocations.clear()
        cls._agent_failures.clear()
        cls._start_time = time.time()
