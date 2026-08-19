"""
AgentOS Phase 7 — Failure Pattern Learning Service.

Classifies and catalogs failure patterns across tasks to accelerate future debugging.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from typing import Any, Dict, List, Optional

from backend.app.models.experience import FailureCategory
from backend.app.services.event_service import EventService

logger = logging.getLogger("agentos.failure_learning")


class FailureLearningService:
    """Classifies, records, and retrieves recurring failure patterns."""

    # category -> list of failure dicts
    _failure_catalog: Dict[FailureCategory, List[Dict[str, Any]]] = defaultdict(list)

    @classmethod
    def record_failure(
        cls,
        task_id: str,
        category: FailureCategory,
        message: str,
        context: Optional[Dict[str, Any]] = None,
        resolution: Optional[str] = None,
    ) -> None:
        """Catalog a failure with its context and eventual resolution."""
        item = {
            "task_id": task_id,
            "category": category.value,
            "message": message,
            "context": context or {},
            "resolution": resolution or "Pending",
        }
        cls._failure_catalog[category].append(item)

        EventService.record_event(
            task_id=task_id,
            event_type="FAILURE_PATTERN_DETECTED",
            payload={"category": category.value, "message": message},
        )

    @classmethod
    def get_resolutions_for_category(cls, category: FailureCategory) -> List[str]:
        """Find successful historical resolution patterns for a given failure class."""
        items = cls._failure_catalog.get(category, [])
        return [it["resolution"] for it in items if it.get("resolution") and it["resolution"] != "Pending"]

    @classmethod
    def get_statistics(cls) -> Dict[str, int]:
        return {cat.value: len(items) for cat, items in cls._failure_catalog.items()}

    @classmethod
    def reset(cls) -> None:
        cls._failure_catalog.clear()
