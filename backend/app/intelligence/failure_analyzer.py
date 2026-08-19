"""
AgentOS Phase 7 - Failure Intelligence.

Classifies recurring failure patterns and keeps the historical resolution
context advisory only.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from backend.app.intelligence.failure_patterns import FailurePatternIntelligence
from backend.app.intelligence.performance_store import PerformanceStore
from backend.app.models.experience import FailureCategory
from backend.app.services.failure_learning import FailureLearningService


class FailurePatternRecord(BaseModel):
    category: str
    frequency: int = 0
    affected_component: str = "unknown"
    previous_resolution: Optional[str] = None
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    pattern: str = "unknown_failure"
    message: Optional[str] = None


class FailureAnalyzer:
    """Structured failure analyzer backed by existing Phase 7 learning data."""

    @classmethod
    def analyze(
        cls,
        message: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> FailurePatternRecord:
        pattern = FailurePatternIntelligence.classify_failure(message, context)
        resolutions = FailurePatternIntelligence.get_resolutions(pattern)
        stats = FailureLearningService.get_statistics()

        affected_component = "unknown"
        if context:
            affected_component = (
                str(context.get("component") or context.get("file_path") or context.get("tool_name") or "unknown")
            )
        else:
            match = re.search(r"([A-Za-z0-9_./\\-]+\.[A-Za-z0-9_]+)", message)
            if match:
                affected_component = match.group(1)

        category = cls._pattern_category(pattern)
        frequency = int(stats.get(category.value, stats.get(category.name, 0)))
        confidence = min(1.0, 0.35 + min(frequency, 10) / 20.0)

        return FailurePatternRecord(
            category=category.value,
            frequency=frequency or 1,
            affected_component=affected_component,
            previous_resolution=resolutions[0] if resolutions else None,
            confidence=round(confidence, 3),
            pattern=pattern.value,
            message=message[:500],
        )

    @classmethod
    def record_failure(
        cls,
        task_id: str,
        message: str,
        context: Optional[Dict[str, Any]] = None,
        resolution: Optional[str] = None,
    ) -> FailurePatternRecord:
        pattern = FailurePatternIntelligence.record_failure(
            task_id=task_id,
            message=message,
            context=context,
            resolution=resolution,
        )
        return cls.analyze(message, context)

    @classmethod
    def list_patterns(cls, limit: int = 50) -> List[FailurePatternRecord]:
        rows = PerformanceStore.list_failure_patterns(limit=limit)
        patterns: List[FailurePatternRecord] = []
        for row in rows:
            patterns.append(
                FailurePatternRecord(
                    category=str(row.get("category", "unknown")),
                    frequency=int(row.get("occurrence_count", 0) or 0),
                    affected_component=str((row.get("metadata") or {}).get("component", "unknown")),
                    previous_resolution=row.get("resolution"),
                    confidence=0.6,
                    pattern=str(row.get("category", "unknown")),
                    message=(row.get("metadata") or {}).get("message"),
                )
            )
        return patterns

    @staticmethod
    def _pattern_category(pattern: Any) -> FailureCategory:
        # Map the lower-level failure pattern into the existing coarse category.
        mapping = {
            "test_failure": FailureCategory.TEST_FAILURE,
            "regression": FailureCategory.REGRESSION,
            "timeout": FailureCategory.TIMEOUT,
            "agent_timeout": FailureCategory.TIMEOUT,
            "dependency_error": FailureCategory.DEPENDENCY_ERROR,
            "security_block": FailureCategory.SECURITY_DENIAL,
            "permission_denied": FailureCategory.SECURITY_DENIAL,
            "patch_conflict": FailureCategory.PATCH_FAILURE,
            "resource_limit": FailureCategory.TOOL_FAILURE,
            "approval_rejected": FailureCategory.PLANNING_FAILURE,
        }
        return mapping.get(getattr(pattern, "value", str(pattern)), FailureCategory.UNKNOWN)
