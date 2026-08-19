"""
AgentOS Phase 7 - Intelligence Repository.

Thin repository shim around the adaptive intelligence persistence helpers.
It keeps the SQLAlchemy-backed storage isolated from the API and service
layers while reusing the existing database session management.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from backend.app.intelligence.performance_store import PerformanceStore


class IntelligenceRepository:
    """Repository facade for adaptive intelligence records."""

    def __init__(self, session: Optional[Any] = None) -> None:
        self.session = session

    def save_routing_decision(self, task_id: str, decision: Dict[str, Any]) -> str:
        return PerformanceStore.save_routing_decision(task_id, decision)

    def list_routing_decisions(self, limit: int = 50) -> List[Dict[str, Any]]:
        return PerformanceStore.list_routing_decisions(limit=limit)

    def get_task_routing(self, task_id: str) -> Optional[Dict[str, Any]]:
        return PerformanceStore.get_task_routing(task_id)

    def save_execution_evaluation(self, task_id: str, evaluation: Dict[str, Any]) -> str:
        return PerformanceStore.save_execution_evaluation(task_id, evaluation)

    def list_execution_evaluations(self, limit: int = 50) -> List[Dict[str, Any]]:
        return PerformanceStore.list_execution_evaluations(limit=limit)

    def list_plan_evaluations(self, limit: int = 50) -> List[Dict[str, Any]]:
        return PerformanceStore.list_plan_evaluations(limit=limit)

    def list_strategy_evaluations(self, limit: int = 50) -> List[Dict[str, Any]]:
        return PerformanceStore.list_strategy_evaluations(limit=limit)

    def list_history(self, limit: int = 50) -> List[Dict[str, Any]]:
        return PerformanceStore.list_task_histories(limit=limit)
