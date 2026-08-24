"""
AgentOS Phase 14 — Production Observability & Telemetry Service.

Collects real, un-simulated system metrics:
- System: CPU, memory, active workers, queue depth, database latency
- Agents: Tasks executed, success/failure rate, retries, replans
- LLM: Providers, model health, tokens, latency, fallback occurrences
- Tools: Invocations, failure rate, timeouts
"""

from __future__ import annotations

import os
import psutil
import time
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from backend.app.config.settings import settings
from backend.app.db.database import get_db_session
from backend.app.db.models import EventModel, ExecutionModel, TaskModel
from backend.app.services.concurrency_manager import ConcurrencyManager
from backend.app.services.database_health import DatabaseHealthService
from backend.app.services.llm_usage import LLMUsageService
from backend.app.services.model_router import ModelRouter


class SystemMetrics(BaseModel):
    cpu_percent: float
    memory_used_mb: float
    memory_percent: float
    active_tasks: int
    queued_tasks: int
    database_status: str
    database_latency_ms: float


class ObservabilityService:
    """Aggregates real-time operational telemetry across all platform layers."""

    @classmethod
    def get_system_metrics(cls) -> SystemMetrics:
        process = psutil.Process(os.getpid())
        mem_info = process.memory_info()
        cpu_pct = process.cpu_percent(interval=None)

        db_health = DatabaseHealthService.probe_health()
        concurrency = ConcurrencyManager.get_metrics()

        return SystemMetrics(
            cpu_percent=round(cpu_pct, 2),
            memory_used_mb=round(mem_info.rss / (1024 * 1024), 2),
            memory_percent=round(process.memory_percent(), 2),
            active_tasks=concurrency.get("active_tasks_count", 0),
            queued_tasks=concurrency.get("queued_tasks_count", 0),
            database_status=db_health.status,
            database_latency_ms=db_health.latency_ms,
        )

    @classmethod
    def get_full_snapshot(cls) -> Dict[str, Any]:
        """Consolidated production observability snapshot."""
        sys_metrics = cls.get_system_metrics()
        model_summary = ModelRouter.get_runtime_summary()
        llm_usage = LLMUsageService.get_summary()

        with get_db_session() as session:
            total_tasks = session.query(TaskModel).count()
            completed_tasks = session.query(TaskModel).filter(TaskModel.status == "COMPLETED").count()
            failed_tasks = session.query(TaskModel).filter(TaskModel.status == "FAILED").count()
            total_executions = session.query(ExecutionModel).count()
            failed_executions = session.query(ExecutionModel).filter(ExecutionModel.status == "FAILED").count()

        success_rate = (completed_tasks / total_tasks * 100.0) if total_tasks > 0 else 100.0

        return {
            "system": sys_metrics.model_dump(),
            "tasks": {
                "total": total_tasks,
                "completed": completed_tasks,
                "failed": failed_tasks,
                "success_rate_pct": round(success_rate, 2),
            },
            "tools": {
                "total_invocations": total_executions,
                "failures": failed_executions,
                "failure_rate_pct": round((failed_executions / total_executions * 100.0) if total_executions > 0 else 0.0, 2),
            },
            "llm": {
                "active_provider": model_summary.get("active_provider"),
                "status": model_summary.get("status"),
                "latency_ms": model_summary.get("latency_ms"),
                "usage_summary": llm_usage,
            },
        }
