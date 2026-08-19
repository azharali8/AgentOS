"""
AgentOS Phase 7 — Failure Pattern Intelligence.

Classifies failures, detects recurring patterns, and tracks successful resolutions.
Historical data is advisory only — never overrides security policies.
"""

from __future__ import annotations

import logging
import re
from enum import Enum
from typing import Any, Dict, List, Optional

from backend.app.intelligence.performance_store import PerformanceStore
from backend.app.models.experience import FailureCategory
from backend.app.services.event_service import EventService
from backend.app.services.failure_learning import FailureLearningService

logger = logging.getLogger("agentos.intelligence.failure_patterns")


class FailurePattern(str, Enum):
    SYNTAX_ERROR = "syntax_error"
    IMPORT_ERROR = "import_error"
    DEPENDENCY_ERROR = "dependency_error"
    TEST_FAILURE = "test_failure"
    REGRESSION = "regression"
    TIMEOUT = "timeout"
    PERMISSION_DENIED = "permission_denied"
    SECURITY_BLOCK = "security_block"
    PATCH_CONFLICT = "patch_conflict"
    STALE_FILE = "stale_file"
    RESOURCE_LIMIT = "resource_limit"
    AGENT_TIMEOUT = "agent_timeout"
    APPROVAL_REJECTED = "approval_rejected"
    UNKNOWN_FAILURE = "unknown_failure"


# Map FailurePattern to existing FailureCategory
_PATTERN_TO_CATEGORY: Dict[FailurePattern, FailureCategory] = {
    FailurePattern.TEST_FAILURE: FailureCategory.TEST_FAILURE,
    FailurePattern.REGRESSION: FailureCategory.REGRESSION,
    FailurePattern.TIMEOUT: FailureCategory.TIMEOUT,
    FailurePattern.AGENT_TIMEOUT: FailureCategory.TIMEOUT,
    FailurePattern.DEPENDENCY_ERROR: FailureCategory.DEPENDENCY_ERROR,
    FailurePattern.SECURITY_BLOCK: FailureCategory.SECURITY_DENIAL,
    FailurePattern.PATCH_CONFLICT: FailureCategory.PATCH_FAILURE,
    FailurePattern.PERMISSION_DENIED: FailureCategory.SECURITY_DENIAL,
    FailurePattern.RESOURCE_LIMIT: FailureCategory.TOOL_FAILURE,
    FailurePattern.APPROVAL_REJECTED: FailureCategory.PLANNING_FAILURE,
    FailurePattern.UNKNOWN_FAILURE: FailureCategory.UNKNOWN,
}

_CLASSIFICATION_RULES: List[tuple[re.Pattern, FailurePattern]] = [
    (re.compile(r"(?i)syntax\s*error|SyntaxError|IndentationError"), FailurePattern.SYNTAX_ERROR),
    (re.compile(r"(?i)import\s*error|ModuleNotFoundError|ImportError"), FailurePattern.IMPORT_ERROR),
    (re.compile(r"(?i)dependency|pip install|requirements"), FailurePattern.DEPENDENCY_ERROR),
    (re.compile(r"(?i)assert|test.*fail|FAILED"), FailurePattern.TEST_FAILURE),
    (re.compile(r"(?i)regression|previously passing"), FailurePattern.REGRESSION),
    (re.compile(r"(?i)timeout|timed out|deadline"), FailurePattern.TIMEOUT),
    (re.compile(r"(?i)permission denied|access denied|forbidden"), FailurePattern.PERMISSION_DENIED),
    (re.compile(r"(?i)security|sensitive|blocked|denied by policy"), FailurePattern.SECURITY_BLOCK),
    (re.compile(r"(?i)patch conflict|merge conflict|hash mismatch"), FailurePattern.PATCH_CONFLICT),
    (re.compile(r"(?i)stale|outdated|file changed"), FailurePattern.STALE_FILE),
    (re.compile(r"(?i)budget exceeded|resource limit|quota"), FailurePattern.RESOURCE_LIMIT),
    (re.compile(r"(?i)agent timeout|execution timeout"), FailurePattern.AGENT_TIMEOUT),
    (re.compile(r"(?i)approval rejected|denied by user"), FailurePattern.APPROVAL_REJECTED),
]


class FailurePatternIntelligence:
    """Classifies failures and tracks recurring patterns with resolutions."""

    @classmethod
    def classify_failure(cls, message: str, context: Optional[Dict[str, Any]] = None) -> FailurePattern:
        """Deterministically classify a failure message."""
        for pattern, failure_type in _CLASSIFICATION_RULES:
            if pattern.search(message):
                return failure_type
        if context:
            if context.get("security_block"):
                return FailurePattern.SECURITY_BLOCK
            if context.get("approval_rejected"):
                return FailurePattern.APPROVAL_REJECTED
        return FailurePattern.UNKNOWN_FAILURE

    @classmethod
    def record_failure(
        cls,
        task_id: str,
        message: str,
        context: Optional[Dict[str, Any]] = None,
        resolution: Optional[str] = None,
    ) -> FailurePattern:
        """Classify, record, and persist a failure pattern."""
        pattern = cls.classify_failure(message, context)
        category = _PATTERN_TO_CATEGORY.get(pattern, FailureCategory.UNKNOWN)

        FailureLearningService.record_failure(
            task_id=task_id,
            category=category,
            message=message,
            context=context,
            resolution=resolution,
        )

        PerformanceStore.save_failure_pattern(pattern.value, {
            "task_id": task_id,
            "message": message[:500],
            "resolution": resolution,
            "context": context or {},
        })

        EventService.record_event(
            task_id=task_id,
            event_type="FAILURE_PATTERN_DETECTED",
            payload={"pattern": pattern.value, "category": category.value},
        )
        return pattern

    @classmethod
    def get_resolutions(cls, pattern: FailurePattern) -> List[str]:
        category = _PATTERN_TO_CATEGORY.get(pattern, FailureCategory.UNKNOWN)
        return FailureLearningService.get_resolutions_for_category(category)

    @classmethod
    def get_statistics(cls) -> Dict[str, int]:
        stats = FailureLearningService.get_statistics()
        persisted = PerformanceStore.list_failure_patterns(limit=100)
        result = dict(stats)
        for p in persisted:
            cat = p.get("category", "unknown")
            result[cat] = result.get(cat, 0) + 1
        return result

    @classmethod
    def reset(cls) -> None:
        FailureLearningService.reset()
