"""
AgentOS Phase 7 - Adaptive Intelligence Service Facade.

Provides a single place for adaptive analysis, history lookup, and bounded
telemetry retrieval. The service reuses existing security checks and does not
expose secrets.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from backend.app.intelligence.execution_history import ExecutionHistory
from backend.app.intelligence.failure_analyzer import FailureAnalyzer
from backend.app.intelligence.intelligence_manager import IntelligenceManager
from backend.app.intelligence.performance_analyzer import PerformanceAnalyzer
from backend.app.intelligence.performance_store import PerformanceStore


class AdaptiveService:
    """Convenience facade for adaptive intelligence operations."""

    @classmethod
    def analyze_task(
        cls,
        task_id: str,
        instruction: str,
        task_category: Optional[str] = None,
        complexity: Optional[str] = None,
        risk_level: Optional[str] = None,
    ) -> Dict[str, Any]:
        result = IntelligenceManager.analyze_task(
            task_id=task_id,
            instruction=instruction,
            task_category=task_category,
            complexity=complexity,
            risk_level=risk_level,
        )
        return result.model_dump(mode="json")

    @classmethod
    def get_task_insights(cls, task_id: str) -> Dict[str, Any]:
        return IntelligenceManager.get_task_insights(task_id)

    @classmethod
    def list_performance(
        cls,
        task_type: Optional[str] = None,
        agent_type: Optional[str] = None,
        model: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        return [
            profile.model_dump(mode="json")
            for profile in PerformanceAnalyzer.analyze(
                task_type=task_type,
                agent_type=agent_type,
                model=model,
                limit=limit,
            )
        ]

    @classmethod
    def list_routing(cls, limit: int = 50) -> List[Dict[str, Any]]:
        return PerformanceStore.list_routing_decisions(limit=limit)

    @classmethod
    def list_failures(cls, limit: int = 50) -> List[Dict[str, Any]]:
        return [pattern.model_dump(mode="json") for pattern in FailureAnalyzer.list_patterns(limit=limit)]

    @classmethod
    def list_evaluations(cls, limit: int = 50) -> List[Dict[str, Any]]:
        return PerformanceStore.list_execution_evaluations(limit=limit)

    @classmethod
    def list_plans(cls, limit: int = 50) -> List[Dict[str, Any]]:
        return PerformanceStore.list_plan_evaluations(limit=limit)

    @classmethod
    def list_history(cls, limit: int = 50) -> List[Dict[str, Any]]:
        return [record.model_dump(mode="json") for record in ExecutionHistory.list_history(limit=limit)]
