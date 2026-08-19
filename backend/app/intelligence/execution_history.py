"""
AgentOS Phase 7 - Execution History Intelligence.

Builds structured knowledge from past task executions without storing secrets.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from backend.app.intelligence.performance_store import PerformanceStore
from backend.app.memory.experience import ExperienceMemory
from backend.app.models.experience import FailureCategory
from backend.app.intelligence.task_history import TaskHistoryService


class ExecutionHistoryRecord(BaseModel):
    task_id: str
    task_category: str
    strategy: str
    agents_involved: List[str] = Field(default_factory=list)
    success: bool = False
    duration_seconds: float = 0.0
    iterations: int = 1
    token_usage: int = 0
    failure_category: Optional[str] = None
    resource_consumption: Dict[str, Any] = Field(default_factory=dict)
    created_at: Optional[Any] = None


class ExecutionHistory:
    """Helper for mining execution history from persisted records."""

    @classmethod
    def record_execution(
        cls,
        task_id: str,
        task_category: str,
        strategy: str,
        agents_involved: List[str],
        success: bool,
        duration_seconds: float = 0.0,
        iterations: int = 1,
        tools_used: Optional[List[str]] = None,
        failure_category: Optional[FailureCategory] = None,
        resource_consumption: Optional[Dict[str, Any]] = None,
    ) -> str:
        return TaskHistoryService.record_execution(
            task_id=task_id,
            task_category=task_category,
            strategy_used=strategy,
            agents_involved=agents_involved,
            success=success,
            duration_seconds=duration_seconds,
            iterations=iterations,
            tools_used=tools_used,
            failure_category=failure_category,
            resource_consumption=resource_consumption,
        )

    @classmethod
    def get_task_history(cls, task_id: str) -> Optional[ExecutionHistoryRecord]:
        history = TaskHistoryService.get_history(task_id)
        if not history:
            return None
        return ExecutionHistoryRecord(
            task_id=history.get("task_id", task_id),
            task_category=history.get("task_category", "general"),
            strategy=history.get("strategy_used", "DIRECT"),
            agents_involved=list(history.get("agents_involved", [])),
            success=bool(history.get("success", False)),
            duration_seconds=float(history.get("duration_seconds", 0.0)),
            iterations=int((history.get("metadata") or {}).get("iterations", 1)),
            token_usage=int((history.get("metadata") or {}).get("resource_consumption", {}).get("tokens_used", 0)),
            failure_category=(history.get("metadata") or {}).get("failure_category"),
            resource_consumption=dict((history.get("metadata") or {}).get("resource_consumption", {})),
            created_at=(history.get("metadata") or {}).get("created_at"),
        )

    @classmethod
    def list_history(cls, limit: int = 50) -> List[ExecutionHistoryRecord]:
        rows = PerformanceStore.list_task_histories(limit=limit)
        records: List[ExecutionHistoryRecord] = []
        for row in rows:
            metadata = row.get("metadata") or {}
            records.append(
                ExecutionHistoryRecord(
                    task_id=row.get("task_id", ""),
                    task_category=row.get("task_category", "general"),
                    strategy=row.get("strategy_used", "DIRECT"),
                    agents_involved=list(row.get("agents_involved", [])),
                    success=bool(row.get("success", False)),
                    duration_seconds=float(row.get("duration_seconds", 0.0)),
                    iterations=int(metadata.get("iterations", 1)),
                    token_usage=int(metadata.get("resource_consumption", {}).get("tokens_used", 0)),
                    failure_category=metadata.get("failure_category"),
                    resource_consumption=dict(metadata.get("resource_consumption", {})),
                    created_at=row.get("created_at"),
                )
            )
        return records

    @classmethod
    def build_knowledge_base(cls, task_category: Optional[str] = None) -> Dict[str, Any]:
        rows = cls.list_history(limit=200)
        if task_category:
            rows = [row for row in rows if row.task_category == task_category]

        if not rows:
            return {
                "task_category": task_category or "general",
                "sample_size": 0,
                "successful_strategies": [],
                "failure_categories": [],
                "average_duration_seconds": 0.0,
                "average_iterations": 0.0,
            }

        success_strategies = Counter(row.strategy for row in rows if row.success)
        failure_categories = Counter(row.failure_category for row in rows if row.failure_category)
        avg_duration = sum(row.duration_seconds for row in rows) / len(rows)
        avg_iterations = sum(row.iterations for row in rows) / len(rows)

        return {
            "task_category": task_category or rows[0].task_category,
            "sample_size": len(rows),
            "successful_strategies": [name for name, _ in success_strategies.most_common()],
            "failure_categories": [name for name, _ in failure_categories.most_common()],
            "average_duration_seconds": round(avg_duration, 3),
            "average_iterations": round(avg_iterations, 3),
            "successful_count": sum(1 for row in rows if row.success),
            "experience_count": len(ExperienceMemory.list_all(limit=1000)),
        }
