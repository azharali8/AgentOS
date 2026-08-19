"""
AgentOS Phase 7 — Experience Memory & Retrieval Engine.

Persists and retrieves task execution experiences:
- Stores bounded ExperienceRecords with centralized secret redaction
- Searches similar historical executions by task_type, strategy, failure_category
- Extracts successful patterns and informs future planning
"""

from __future__ import annotations

import logging
from collections import defaultdict
from typing import Any, Dict, List, Optional

from backend.app.models.experience import ExperienceRecord, FailureCategory
from backend.app.observability.redaction import redact_secrets
from backend.app.services.event_service import EventService

logger = logging.getLogger("agentos.experience_memory")


class ExperienceMemory:
    """In-memory and indexed experience storage with secret scrubbing."""

    _records: Dict[str, ExperienceRecord] = {}

    @classmethod
    def store_experience(cls, record: ExperienceRecord) -> str:
        """Store an experience record after scrubbing secrets."""
        # Sanitize summary and lessons
        cleaned_dict = redact_secrets(record.model_dump())
        cleaned_record = ExperienceRecord(**cleaned_dict)

        cls._records[cleaned_record.experience_id] = cleaned_record

        EventService.record_event(
            task_id=cleaned_record.task_id,
            event_type="EXPERIENCE_STORED",
            payload={
                "experience_id": cleaned_record.experience_id,
                "task_type": cleaned_record.task_type,
                "strategy": cleaned_record.strategy,
                "success": cleaned_record.success,
            },
        )
        return cleaned_record.experience_id

    @classmethod
    def get_experience(cls, experience_id: str) -> Optional[ExperienceRecord]:
        return cls._records.get(experience_id)

    @classmethod
    def search_similar(
        cls,
        task_type: Optional[str] = None,
        strategy: Optional[str] = None,
        only_successful: bool = False,
        limit: int = 10,
    ) -> List[ExperienceRecord]:
        """Query past experience records based on metadata filtering."""
        matches = []
        for r in reversed(list(cls._records.values())):
            if task_type and r.task_type.lower() != task_type.lower():
                continue
            if strategy and r.strategy.lower() != strategy.lower():
                continue
            if only_successful and not r.success:
                continue
            matches.append(r)
            if len(matches) >= limit:
                break
        return matches

    @classmethod
    def get_successful_strategies(cls, task_type: str) -> List[str]:
        """Retrieve most successful strategies for a given task type."""
        strategy_counts: Dict[str, int] = defaultdict(int)
        for r in cls._records.values():
            if r.task_type.lower() == task_type.lower() and r.success:
                strategy_counts[r.strategy] += 1
        sorted_strats = sorted(strategy_counts.items(), key=lambda x: x[1], reverse=True)
        return [s[0] for s in sorted_strats]

    @classmethod
    def get_failure_patterns(cls, failure_category: Optional[FailureCategory] = None) -> List[ExperienceRecord]:
        """Retrieve historical failure cases for root-cause learning."""
        failures = []
        for r in cls._records.values():
            if not r.success:
                if failure_category is None or r.failure_category == failure_category:
                    failures.append(r)
        return failures

    @classmethod
    def list_all(cls, limit: int = 50) -> List[ExperienceRecord]:
        return list(cls._records.values())[-limit:]

    @classmethod
    def reset(cls) -> None:
        cls._records.clear()
