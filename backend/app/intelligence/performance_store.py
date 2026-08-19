"""
AgentOS Phase 7 — SQLite-backed Intelligence Performance Store.

Persists agent performance, task history, failure patterns, and evaluations
using the existing repository pattern. No secrets or raw sensitive data stored.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from backend.app.db.database import get_db_session
from backend.app.db.models import (
    AgentPerformanceModel,
    ExecutionEvaluationModel,
    FailurePatternModel,
    PlanEvaluationModel,
    RoutingDecisionModel,
    StrategyEvaluationModel,
    TaskHistoryModel,
    TaskStrategyModel,
)
from backend.app.observability.redaction import redact_secrets

logger = logging.getLogger("agentos.intelligence.store")


def _serialize(data: Any) -> Any:
    """Ensure JSON-serializable payload with secret redaction."""
    if hasattr(data, "model_dump"):
        return redact_secrets(data.model_dump(mode="json"))
    return redact_secrets(data)


class PerformanceStore:
    """Central SQLite persistence layer for intelligence data."""

    @classmethod
    def save_agent_performance(cls, agent_type: str, metrics: Dict[str, Any]) -> str:
        record_id = f"perf-{uuid.uuid4().hex[:12]}"
        with get_db_session() as session:
            model = AgentPerformanceModel(
                record_id=record_id,
                agent_type=agent_type,
                metrics=_serialize(metrics),
                updated_at=datetime.now(timezone.utc),
            )
            session.add(model)
            session.commit()
        return record_id

    @classmethod
    def get_latest_performance(cls, agent_type: str) -> Optional[Dict[str, Any]]:
        with get_db_session() as session:
            row = (
                session.query(AgentPerformanceModel)
                .filter(AgentPerformanceModel.agent_type == agent_type)
                .order_by(AgentPerformanceModel.updated_at.desc())
                .first()
            )
            return row.metrics if row else None

    @classmethod
    def list_agent_performances(cls, limit: int = 50) -> List[Dict[str, Any]]:
        with get_db_session() as session:
            rows = (
                session.query(AgentPerformanceModel)
                .order_by(AgentPerformanceModel.updated_at.desc())
                .limit(limit)
                .all()
            )
            return [{"record_id": r.record_id, "agent_type": r.agent_type, "metrics": r.metrics} for r in rows]

    @classmethod
    def save_task_history(cls, task_id: str, record: Dict[str, Any]) -> str:
        history_id = f"hist-{uuid.uuid4().hex[:12]}"
        with get_db_session() as session:
            model = TaskHistoryModel(
                history_id=history_id,
                task_id=task_id,
                task_category=record.get("task_category", "general"),
                strategy_used=record.get("strategy_used", "DIRECT"),
                agents_involved=record.get("agents_involved", []),
                success=record.get("success", False),
                duration_seconds=record.get("duration_seconds", 0.0),
                history_metadata=_serialize(record),
                created_at=datetime.now(timezone.utc),
            )
            session.add(model)
            session.commit()
        return history_id

    @classmethod
    def get_task_history(cls, task_id: str) -> Optional[Dict[str, Any]]:
        with get_db_session() as session:
            row = (
                session.query(TaskHistoryModel)
                .filter(TaskHistoryModel.task_id == task_id)
                .order_by(TaskHistoryModel.created_at.desc())
                .first()
            )
            if not row:
                return None
            return {
                "history_id": row.history_id,
                "task_id": row.task_id,
                "task_category": row.task_category,
                "strategy_used": row.strategy_used,
                "agents_involved": row.agents_involved,
                "success": row.success,
                "duration_seconds": row.duration_seconds,
                "metadata": row.history_metadata,
            }

    @classmethod
    def save_task_strategy(cls, task_id: str, strategy: str, metadata: Dict[str, Any]) -> str:
        strategy_id = f"strat-{uuid.uuid4().hex[:12]}"
        with get_db_session() as session:
            model = TaskStrategyModel(
                strategy_id=strategy_id,
                task_id=task_id,
                strategy=strategy,
                strategy_metadata=_serialize(metadata),
                created_at=datetime.now(timezone.utc),
            )
            session.add(model)
            session.commit()
        return strategy_id

    @classmethod
    def get_task_strategy(cls, task_id: str) -> Optional[Dict[str, Any]]:
        with get_db_session() as session:
            row = (
                session.query(TaskStrategyModel)
                .filter(TaskStrategyModel.task_id == task_id)
                .order_by(TaskStrategyModel.created_at.desc())
                .first()
            )
            if not row:
                return None
            return {"strategy_id": row.strategy_id, "task_id": row.task_id, "strategy": row.strategy, "metadata": row.strategy_metadata}

    @classmethod
    def save_failure_pattern(cls, category: str, pattern: Dict[str, Any]) -> str:
        pattern_id = f"fail-{uuid.uuid4().hex[:12]}"
        with get_db_session() as session:
            model = FailurePatternModel(
                pattern_id=pattern_id,
                category=category,
                occurrence_count=1,
                resolution=pattern.get("resolution"),
                pattern_metadata=_serialize(pattern),
                updated_at=datetime.now(timezone.utc),
            )
            session.add(model)
            session.commit()
        return pattern_id

    @classmethod
    def list_failure_patterns(cls, limit: int = 50) -> List[Dict[str, Any]]:
        with get_db_session() as session:
            rows = (
                session.query(FailurePatternModel)
                .order_by(FailurePatternModel.updated_at.desc())
                .limit(limit)
                .all()
            )
            return [
                {
                    "pattern_id": r.pattern_id,
                    "category": r.category,
                    "occurrence_count": r.occurrence_count,
                    "resolution": r.resolution,
                    "metadata": r.pattern_metadata,
                }
                for r in rows
            ]

    @classmethod
    def save_strategy_evaluation(cls, task_id: str, evaluation: Dict[str, Any]) -> str:
        eval_id = f"seval-{uuid.uuid4().hex[:12]}"
        with get_db_session() as session:
            model = StrategyEvaluationModel(
                eval_id=eval_id,
                task_id=task_id,
                strategy=evaluation.get("strategy", "DIRECT"),
                score=evaluation.get("score", 0.0),
                eval_metadata=_serialize(evaluation),
                created_at=datetime.now(timezone.utc),
            )
            session.add(model)
            session.commit()
        return eval_id

    @classmethod
    def save_plan_evaluation(cls, task_id: str, evaluation: Dict[str, Any]) -> str:
        eval_id = f"peval-{uuid.uuid4().hex[:12]}"
        with get_db_session() as session:
            model = PlanEvaluationModel(
                eval_id=eval_id,
                task_id=task_id,
                score=evaluation.get("score", 0.0),
                plan_metadata=_serialize(evaluation),
                created_at=datetime.now(timezone.utc),
            )
            session.add(model)
            session.commit()
        return eval_id

    @classmethod
    def save_routing_decision(cls, task_id: str, decision: Dict[str, Any]) -> str:
        decision_id = f"route-{uuid.uuid4().hex[:12]}"
        with get_db_session() as session:
            model = RoutingDecisionModel(
                decision_id=decision_id,
                task_id=task_id,
                task_category=decision.get("task_category", "general"),
                provider=decision.get("provider", "unknown"),
                model=decision.get("model", "unknown"),
                reason=decision.get("reason", ""),
                confidence=float(decision.get("confidence", 0.0)),
                estimated_cost=float(decision.get("estimated_cost", 0.0)),
                estimated_latency_ms=float(decision.get("estimated_latency_ms", 0.0)),
                routing_metadata=_serialize(decision),
                created_at=datetime.now(timezone.utc),
            )
            session.add(model)
            session.commit()
        return decision_id

    @classmethod
    def get_task_routing(cls, task_id: str) -> Optional[Dict[str, Any]]:
        with get_db_session() as session:
            row = (
                session.query(RoutingDecisionModel)
                .filter(RoutingDecisionModel.task_id == task_id)
                .order_by(RoutingDecisionModel.created_at.desc())
                .first()
            )
            if not row:
                return None
            return {
                "decision_id": row.decision_id,
                "task_id": row.task_id,
                "task_category": row.task_category,
                "provider": row.provider,
                "model": row.model,
                "reason": row.reason,
                "confidence": row.confidence,
                "estimated_cost": row.estimated_cost,
                "estimated_latency_ms": row.estimated_latency_ms,
                "metadata": row.routing_metadata,
            }

    @classmethod
    def list_routing_decisions(cls, limit: int = 50) -> List[Dict[str, Any]]:
        with get_db_session() as session:
            rows = (
                session.query(RoutingDecisionModel)
                .order_by(RoutingDecisionModel.created_at.desc())
                .limit(limit)
                .all()
            )
            return [
                {
                    "decision_id": r.decision_id,
                    "task_id": r.task_id,
                    "task_category": r.task_category,
                    "provider": r.provider,
                    "model": r.model,
                    "reason": r.reason,
                    "confidence": r.confidence,
                    "estimated_cost": r.estimated_cost,
                    "estimated_latency_ms": r.estimated_latency_ms,
                    "metadata": r.routing_metadata,
                    "created_at": r.created_at,
                }
                for r in rows
            ]

    @classmethod
    def save_execution_evaluation(cls, task_id: str, evaluation: Dict[str, Any]) -> str:
        eval_id = f"eeval-{uuid.uuid4().hex[:12]}"
        with get_db_session() as session:
            model = ExecutionEvaluationModel(
                evaluation_id=eval_id,
                task_id=task_id,
                success=bool(evaluation.get("success", False)),
                quality_score=float(evaluation.get("quality_score", evaluation.get("overall_quality", 0.0))),
                efficiency_score=float(evaluation.get("efficiency_score", evaluation.get("execution_efficiency", 0.0))),
                safety_score=float(evaluation.get("safety_score", evaluation.get("security", 0.0))),
                coordination_score=float(evaluation.get("coordination_score", evaluation.get("routing_quality", 0.0))),
                recommendations=_serialize(evaluation.get("recommendations", evaluation.get("lessons", []))),
                evaluation_metadata=_serialize(evaluation),
                created_at=datetime.now(timezone.utc),
            )
            session.add(model)
            session.commit()
        return eval_id

    @classmethod
    def get_task_execution_evaluation(cls, task_id: str) -> Optional[Dict[str, Any]]:
        with get_db_session() as session:
            row = (
                session.query(ExecutionEvaluationModel)
                .filter(ExecutionEvaluationModel.task_id == task_id)
                .order_by(ExecutionEvaluationModel.created_at.desc())
                .first()
            )
            if not row:
                return None
            return {
                "evaluation_id": row.evaluation_id,
                "task_id": row.task_id,
                "success": row.success,
                "quality_score": row.quality_score,
                "efficiency_score": row.efficiency_score,
                "safety_score": row.safety_score,
                "coordination_score": row.coordination_score,
                "recommendations": row.recommendations,
                "metadata": row.evaluation_metadata,
            }

    @classmethod
    def list_execution_evaluations(cls, limit: int = 50) -> List[Dict[str, Any]]:
        with get_db_session() as session:
            rows = (
                session.query(ExecutionEvaluationModel)
                .order_by(ExecutionEvaluationModel.created_at.desc())
                .limit(limit)
                .all()
            )
            return [
                {
                    "evaluation_id": r.evaluation_id,
                    "task_id": r.task_id,
                    "success": r.success,
                    "quality_score": r.quality_score,
                    "efficiency_score": r.efficiency_score,
                    "safety_score": r.safety_score,
                    "coordination_score": r.coordination_score,
                    "recommendations": r.recommendations,
                    "metadata": r.evaluation_metadata,
                    "created_at": r.created_at,
                }
                for r in rows
            ]

    @classmethod
    def list_task_histories(cls, limit: int = 50) -> List[Dict[str, Any]]:
        with get_db_session() as session:
            rows = (
                session.query(TaskHistoryModel)
                .order_by(TaskHistoryModel.created_at.desc())
                .limit(limit)
                .all()
            )
            return [
                {
                    "history_id": r.history_id,
                    "task_id": r.task_id,
                    "task_category": r.task_category,
                    "strategy_used": r.strategy_used,
                    "agents_involved": r.agents_involved,
                    "success": r.success,
                    "duration_seconds": r.duration_seconds,
                    "metadata": r.history_metadata,
                    "created_at": r.created_at,
                }
                for r in rows
            ]

    @classmethod
    def list_task_strategies(cls, limit: int = 50) -> List[Dict[str, Any]]:
        with get_db_session() as session:
            rows = (
                session.query(TaskStrategyModel)
                .order_by(TaskStrategyModel.created_at.desc())
                .limit(limit)
                .all()
            )
            return [
                {
                    "strategy_id": r.strategy_id,
                    "task_id": r.task_id,
                    "strategy": r.strategy,
                    "metadata": r.strategy_metadata,
                    "created_at": r.created_at,
                }
                for r in rows
            ]

    @classmethod
    def list_plan_evaluations(cls, limit: int = 50) -> List[Dict[str, Any]]:
        with get_db_session() as session:
            rows = (
                session.query(PlanEvaluationModel)
                .order_by(PlanEvaluationModel.created_at.desc())
                .limit(limit)
                .all()
            )
            return [
                {
                    "evaluation_id": r.eval_id,
                    "task_id": r.task_id,
                    "score": r.score,
                    "metadata": r.plan_metadata,
                    "created_at": r.created_at,
                }
                for r in rows
            ]

    @classmethod
    def list_strategy_evaluations(cls, limit: int = 50) -> List[Dict[str, Any]]:
        with get_db_session() as session:
            rows = (
                session.query(StrategyEvaluationModel)
                .order_by(StrategyEvaluationModel.created_at.desc())
                .limit(limit)
                .all()
            )
            return [
                {
                    "evaluation_id": r.eval_id,
                    "task_id": r.task_id,
                    "strategy": r.strategy,
                    "score": r.score,
                    "metadata": r.eval_metadata,
                    "created_at": r.created_at,
                }
                for r in rows
            ]
