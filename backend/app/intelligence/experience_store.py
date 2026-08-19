"""
AgentOS Phase 8 - Experience Store.

Persistent, bounded storage for execution experiences. The store is advisory
only and mirrors a redacted projection into the legacy experience memory so
Phase 7 callers continue to work without a parallel persistence system.
"""

from __future__ import annotations

import logging
import math
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from backend.app.config.settings import settings
from backend.app.db.database import get_db_session
from backend.app.db.models import LearningExperienceModel
from backend.app.db.repositories.experience_repository import ExperienceRepository
from backend.app.evaluation.adaptive_metrics import AdaptiveMetricsCollector
from backend.app.intelligence.experience_models import ExecutionExperience, hash_task_description
from backend.app.memory.experience import ExperienceMemory
from backend.app.models.experience import ExperienceRecord, FailureCategory
from backend.app.observability.redaction import redact_secrets
from backend.app.security.sensitive_files import is_sensitive_path
from backend.app.services.event_service import EventService

logger = logging.getLogger("agentos.learning.experience_store")


def _sanitize_text(value: Any) -> Any:
    if isinstance(value, str) and value and is_sensitive_path(value):
        return "[REDACTED_PATH]"
    return value


def _deep_sanitize(value: Any) -> Any:
    cleaned = redact_secrets(value)
    if isinstance(cleaned, dict):
        return {str(k): _deep_sanitize(v) if not isinstance(v, str) else _sanitize_text(v) for k, v in cleaned.items()}
    if isinstance(cleaned, list):
        return [_deep_sanitize(item) if not isinstance(item, str) else _sanitize_text(item) for item in cleaned]
    if isinstance(cleaned, tuple):
        return tuple(_deep_sanitize(item) if not isinstance(item, str) else _sanitize_text(item) for item in cleaned)
    return _sanitize_text(cleaned)


def _coerce_hash(experience: Dict[str, Any]) -> str:
    task_hash = experience.get("task_description_hash")
    if isinstance(task_hash, str) and len(task_hash.strip()) == 64:
        return task_hash.strip().lower()

    source = (
        experience.get("task_summary")
        or experience.get("final_outcome")
        or experience.get("learning_metadata", {}).get("instruction")
        or experience.get("task_id", "")
    )
    return hash_task_description(str(source))


def _legacy_failure_category(experience: ExecutionExperience) -> Optional[FailureCategory]:
    candidate = (experience.failure_pattern or experience.failure_type or "").upper()
    mapping = {
        "TEST_FAILURE": FailureCategory.TEST_FAILURE,
        "TEST_FAILURES": FailureCategory.TEST_FAILURE,
        "PATCH_FAILURE": FailureCategory.PATCH_FAILURE,
        "TOOL_FAILURE": FailureCategory.TOOL_FAILURE,
        "SECURITY_DENIAL": FailureCategory.SECURITY_DENIAL,
        "TIMEOUT": FailureCategory.TIMEOUT,
        "DEPENDENCY_ERROR": FailureCategory.DEPENDENCY_ERROR,
        "ENVIRONMENT_ERROR": FailureCategory.ENVIRONMENT_ERROR,
        "REGRESSION": FailureCategory.REGRESSION,
        "AGENT_FAILURE": FailureCategory.AGENT_FAILURE,
        "PLANNING_FAILURE": FailureCategory.PLANNING_FAILURE,
        "ROUTING_FAILURE": FailureCategory.ROUTING_FAILURE,
    }
    return mapping.get(candidate)


def _to_legacy_experience(experience: ExecutionExperience) -> ExperienceRecord:
    task_summary = experience.task_summary or experience.final_outcome or ""
    lessons: List[str] = []
    if experience.learning_metadata.get("lessons"):
        lessons = [str(item) for item in experience.learning_metadata.get("lessons", [])][:10]

    return ExperienceRecord(
        experience_id=experience.experience_id,
        task_id=experience.task_id,
        task_type=experience.task_type,
        task_classification=experience.task_type,
        project_type=experience.project_type,
        instruction_summary=task_summary[:500],
        agents_used=[str(agent) for agent in experience.selected_agents],
        decomposition_summary=[str(item) for item in experience.decomposition_summary][:10],
        strategy=experience.selected_strategy,
        tools_used=[str(tool) for tool in experience.learning_metadata.get("tools_used", [])][:20],
        outcome=experience.final_outcome or ("SUCCESS" if experience.success else "FAILED"),
        success=experience.success,
        failure_category=_legacy_failure_category(experience),
        iterations=int(experience.learning_metadata.get("iterations", 1) or 1),
        retries=int(experience.learning_metadata.get("retries", 0) or 0),
        duration_seconds=float(experience.execution_duration),
        token_usage=int(experience.token_usage),
        estimated_cost=float(experience.learning_metadata.get("estimated_cost", 0.0) or 0.0),
        approval_required=experience.approval_required,
        regression_detected=experience.regression_detected,
        lessons_learned=lessons,
        created_at=experience.timestamp,
    )


class ExperienceStore:
    """Central Phase 8 persistence facade for execution experiences."""

    @classmethod
    def build_experience(
        cls,
        *,
        task_id: str,
        task_type: str,
        task_description: str | None = None,
        task_description_hash: Optional[str] = None,
        task_complexity: str = "medium",
        project_type: str = "python",
        framework: Optional[str] = None,
        selected_strategy: str = "DIRECT",
        selected_model: Optional[str] = None,
        selected_agents: Optional[List[str]] = None,
        decomposition_summary: Optional[List[str]] = None,
        plan_score: float = 0.0,
        resource_budget: Optional[Dict[str, Any]] = None,
        execution_duration: float = 0.0,
        tool_call_count: int = 0,
        token_usage: int = 0,
        success: bool = False,
        failure_type: Optional[str] = None,
        failure_pattern: Optional[str] = None,
        regression_detected: bool = False,
        approval_required: bool = False,
        approval_outcome: Optional[str] = None,
        security_events: Optional[List[str]] = None,
        evaluation_score: float = 0.0,
        final_outcome: str = "UNKNOWN",
        parent_task_id: Optional[str] = None,
        evidence_ids: Optional[List[str]] = None,
        task_summary: Optional[str] = None,
        learning_metadata: Optional[Dict[str, Any]] = None,
        experience_id: Optional[str] = None,
    ) -> ExecutionExperience:
        redacted_summary = redact_secrets(task_summary or task_description or final_outcome or "")
        description_hash = task_description_hash or hash_task_description(str(redacted_summary or task_id))
        metadata = dict(learning_metadata or {})
        metadata.setdefault("iterations", metadata.get("iterations", 1))
        metadata.setdefault("retries", metadata.get("retries", 0))

        return ExecutionExperience(
            experience_id=experience_id or f"exp-{uuid.uuid4().hex[:12]}",
            task_id=task_id,
            parent_task_id=parent_task_id,
            task_type=task_type,
            task_description_hash=description_hash,
            task_complexity=task_complexity,
            project_type=project_type,
            framework=framework,
            selected_strategy=selected_strategy,
            selected_model=selected_model,
            selected_agents=selected_agents or [],
            decomposition_summary=decomposition_summary or [],
            plan_score=max(0.0, float(plan_score)),
            resource_budget=_deep_sanitize(resource_budget or {}),
            execution_duration=max(0.0, float(execution_duration)),
            tool_call_count=max(0, int(tool_call_count)),
            token_usage=max(0, int(token_usage)),
            success=bool(success),
            failure_type=failure_type,
            failure_pattern=failure_pattern,
            regression_detected=bool(regression_detected),
            approval_required=bool(approval_required),
            approval_outcome=approval_outcome,
            security_events=[str(item) for item in (security_events or [])][:20],
            evaluation_score=max(0.0, float(evaluation_score)),
            final_outcome=redact_secrets(final_outcome or ("SUCCESS" if success else "FAILED")),
            evidence_ids=[str(item) for item in (evidence_ids or [])][:20],
            task_summary=redacted_summary[:500] if isinstance(redacted_summary, str) else None,
            learning_metadata=_deep_sanitize(metadata),
        )

    @classmethod
    def record_experience(cls, experience: ExecutionExperience | Dict[str, Any]) -> ExecutionExperience:
        """Persist a new learning experience and mirror it into legacy memory."""
        payload = experience.model_dump(mode="json") if isinstance(experience, ExecutionExperience) else dict(experience)
        payload = _deep_sanitize(payload)
        payload["task_description_hash"] = _coerce_hash(payload)
        exp = ExecutionExperience(**payload)

        with get_db_session() as session:
            repo = ExperienceRepository(session)
            model = LearningExperienceModel(
                experience_id=exp.experience_id,
                task_id=exp.task_id,
                parent_task_id=exp.parent_task_id,
                task_type=exp.task_type,
                task_description_hash=exp.task_description_hash,
                task_complexity=exp.task_complexity,
                project_type=exp.project_type,
                framework=exp.framework,
                selected_strategy=exp.selected_strategy,
                selected_model=exp.selected_model,
                selected_agents=exp.selected_agents,
                decomposition_summary=exp.decomposition_summary,
                plan_score=exp.plan_score,
                resource_budget=exp.resource_budget,
                execution_duration=exp.execution_duration,
                tool_call_count=exp.tool_call_count,
                token_usage=exp.token_usage,
                success=exp.success,
                failure_type=exp.failure_type,
                failure_pattern=exp.failure_pattern,
                regression_detected=exp.regression_detected,
                approval_required=exp.approval_required,
                approval_outcome=exp.approval_outcome,
                security_events=exp.security_events,
                evaluation_score=exp.evaluation_score,
                final_outcome=exp.final_outcome,
                task_summary=exp.task_summary,
                evidence_ids=exp.evidence_ids,
                learning_metadata=exp.learning_metadata,
                timestamp=exp.timestamp,
            )
            repo.create(model)

        cls._mirror_to_legacy_memory(exp)
        AdaptiveMetricsCollector.record_experience_recorded()
        EventService.record_event(
            task_id=exp.task_id,
            event_type="LEARNING_EXPERIENCE_RECORDED",
            payload={
                "experience_id": exp.experience_id,
                "task_type": exp.task_type,
                "strategy": exp.selected_strategy,
                "success": exp.success,
            },
        )
        cls.prune()
        return exp

    @classmethod
    def update_experience(
        cls,
        experience_id: str,
        updates: Dict[str, Any],
    ) -> Optional[ExecutionExperience]:
        cleaned = _deep_sanitize(dict(updates))
        with get_db_session() as session:
            repo = ExperienceRepository(session)
            row = repo.get_by_id(experience_id)
            if row is None:
                return None

            for key, value in cleaned.items():
                if hasattr(row, key):
                    setattr(row, key, value)
            repo.update(row)
            updated = cls._model_to_experience(row)

        cls._mirror_to_legacy_memory(updated)
        EventService.record_event(
            task_id=updated.task_id,
            event_type="LEARNING_EXPERIENCE_UPDATED",
            payload={
                "experience_id": updated.experience_id,
                "task_type": updated.task_type,
                "success": updated.success,
            },
        )
        return updated

    @classmethod
    def update_task_experience(
        cls,
        task_id: str,
        updates: Dict[str, Any],
        *,
        create_if_missing: bool = True,
    ) -> Optional[ExecutionExperience]:
        with get_db_session() as session:
            repo = ExperienceRepository(session)
            row = repo.get_latest_by_task_id(task_id)
            if row is None:
                if not create_if_missing:
                    return None
                payload = dict(updates)
                payload.setdefault("task_id", task_id)
                return cls.record_experience(payload)

            for key, value in _deep_sanitize(dict(updates)).items():
                if hasattr(row, key):
                    setattr(row, key, value)
            repo.update(row)
            updated = cls._model_to_experience(row)

        cls._mirror_to_legacy_memory(updated)
        AdaptiveMetricsCollector.record_experience_recorded()
        EventService.record_event(
            task_id=task_id,
            event_type="LEARNING_EXPERIENCE_UPDATED",
            payload={
                "experience_id": updated.experience_id,
                "task_type": updated.task_type,
                "success": updated.success,
            },
        )
        return updated

    @classmethod
    def get_experience(cls, experience_id: str) -> Optional[ExecutionExperience]:
        with get_db_session() as session:
            repo = ExperienceRepository(session)
            row = repo.get_by_id(experience_id)
            if not row:
                return None
            return cls._model_to_experience(row)

    @classmethod
    def get_task_experiences(cls, task_id: str, limit: int = 10) -> List[ExecutionExperience]:
        with get_db_session() as session:
            repo = ExperienceRepository(session)
            rows = repo.list_experiences(limit=limit, task_id=task_id)
            return [cls._model_to_experience(row) for row in rows]

    @classmethod
    def list_experiences(
        cls,
        limit: int = 50,
        offset: int = 0,
        task_type: Optional[str] = None,
        task_complexity: Optional[str] = None,
        selected_strategy: Optional[str] = None,
        success: Optional[bool] = None,
        project_type: Optional[str] = None,
        framework: Optional[str] = None,
        task_id: Optional[str] = None,
    ) -> List[ExecutionExperience]:
        bounded_limit = max(1, min(limit, getattr(settings, "MAX_LEARNING_RETRIEVAL_TOP_K", 50)))
        with get_db_session() as session:
            repo = ExperienceRepository(session)
            rows = repo.list_experiences(
                limit=bounded_limit,
                offset=max(0, offset),
                task_type=task_type,
                task_complexity=task_complexity,
                selected_strategy=selected_strategy,
                success=success,
                project_type=project_type,
                framework=framework,
                task_id=task_id,
            )
            return [cls._model_to_experience(row) for row in rows]

    @classmethod
    def count(cls) -> int:
        with get_db_session() as session:
            repo = ExperienceRepository(session)
            return repo.count()

    @classmethod
    def prune(cls) -> int:
        """Apply retention and bounded storage limits."""
        deleted = 0
        retention_days = int(getattr(settings, "LEARNING_RETENTION_DAYS", 90))
        max_records = int(getattr(settings, "MAX_LEARNING_EXPERIENCES", 1000))
        cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)

        with get_db_session() as session:
            repo = ExperienceRepository(session)
            expired = repo.list_older_than(cutoff)
            for row in expired:
                repo.delete(row)
                deleted += 1

            current_count = repo.count()
            if current_count > max_records:
                excess = current_count - max_records
                stale_rows = repo.list_experiences(limit=excess, offset=max(0, current_count - excess))
                for row in stale_rows:
                    repo.delete(row)
                    deleted += 1

        if deleted:
            EventService.record_event(
                task_id="system",
                event_type="LEARNING_EXPERIENCE_PRUNED",
                payload={"deleted": deleted, "retention_days": retention_days, "max_records": max_records},
            )
        return deleted

    @classmethod
    def _mirror_to_legacy_memory(cls, experience: ExecutionExperience) -> None:
        try:
            ExperienceMemory.store_experience(_to_legacy_experience(experience))
        except Exception as exc:  # pragma: no cover - legacy mirror should never break persistence
            logger.warning("Failed to mirror learning experience into legacy memory: %s", exc)

    @staticmethod
    def _model_to_experience(row: LearningExperienceModel) -> ExecutionExperience:
        return ExecutionExperience(
            experience_id=row.experience_id,
            task_id=row.task_id,
            parent_task_id=row.parent_task_id,
            task_type=row.task_type,
            task_description_hash=row.task_description_hash,
            task_complexity=row.task_complexity,
            project_type=row.project_type,
            framework=row.framework,
            selected_strategy=row.selected_strategy,
            selected_model=row.selected_model,
            selected_agents=list(row.selected_agents or []),
            decomposition_summary=list(row.decomposition_summary or []),
            plan_score=float(row.plan_score or 0.0),
            resource_budget=dict(row.resource_budget or {}),
            execution_duration=float(row.execution_duration or 0.0),
            tool_call_count=int(row.tool_call_count or 0),
            token_usage=int(row.token_usage or 0),
            success=bool(row.success),
            failure_type=row.failure_type,
            failure_pattern=row.failure_pattern,
            regression_detected=bool(row.regression_detected),
            approval_required=bool(row.approval_required),
            approval_outcome=row.approval_outcome,
            security_events=list(row.security_events or []),
            evaluation_score=float(row.evaluation_score or 0.0),
            final_outcome=row.final_outcome,
            evidence_ids=list(row.evidence_ids or []),
            task_summary=row.task_summary,
            learning_metadata=dict(row.learning_metadata or {}),
            timestamp=row.timestamp,
        )
