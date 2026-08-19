"""
AgentOS Phase 2 — Metrics Service

Lightweight metrics gathering from SQLite database and runtime counters.
"""

from __future__ import annotations

from typing import Any, Dict
from sqlalchemy import func

from backend.app.db.database import get_db_session
from backend.app.db.models import TaskModel, ApprovalModel, ExecutionModel


class MetricsService:

    @classmethod
    def get_metrics(cls) -> Dict[str, Any]:
        """Aggregate metrics across tasks, approvals, and executions."""
        with get_db_session() as session:
            # Task metrics
            tasks_total = session.query(func.count(TaskModel.task_id)).scalar() or 0
            tasks_completed = (
                session.query(func.count(TaskModel.task_id))
                .filter(TaskModel.status == "COMPLETED")
                .scalar()
                or 0
            )
            tasks_failed = (
                session.query(func.count(TaskModel.task_id))
                .filter(TaskModel.status == "FAILED")
                .scalar()
                or 0
            )
            tasks_cancelled = (
                session.query(func.count(TaskModel.task_id))
                .filter(TaskModel.status == "CANCELLED")
                .scalar()
                or 0
            )

            # Approval metrics
            approvals_requested = (
                session.query(func.count(ApprovalModel.approval_id)).scalar() or 0
            )
            approvals_approved = (
                session.query(func.count(ApprovalModel.approval_id))
                .filter(ApprovalModel.status == "APPROVED")
                .scalar()
                or 0
            )
            approvals_rejected = (
                session.query(func.count(ApprovalModel.approval_id))
                .filter(ApprovalModel.status == "REJECTED")
                .scalar()
                or 0
            )

            # Execution metrics
            tool_calls_total = (
                session.query(func.count(ExecutionModel.execution_id)).scalar() or 0
            )
            tool_failures = (
                session.query(func.count(ExecutionModel.execution_id))
                .filter(ExecutionModel.status == "FAILED")
                .scalar()
                or 0
            )
            avg_tool_duration = (
                session.query(func.avg(ExecutionModel.duration_ms)).scalar() or 0.0
            )

            return {
                "tasks_total": tasks_total,
                "tasks_completed": tasks_completed,
                "tasks_failed": tasks_failed,
                "tasks_cancelled": tasks_cancelled,
                "approvals_requested": approvals_requested,
                "approvals_approved": approvals_approved,
                "approvals_rejected": approvals_rejected,
                "tool_calls_total": tool_calls_total,
                "tool_failures": tool_failures,
                "average_tool_duration_ms": float(avg_tool_duration),
            }
