"""
AgentOS Phase 8 - Learning Safety Gate.

Validates learned recommendations before they can influence routing or
planning. The gate is advisory-only and never relaxes authoritative policy.
"""

from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List, Optional

from pydantic import BaseModel, ConfigDict, Field

from backend.app.config.settings import settings
from backend.app.intelligence.experience_models import LearningRecommendation
from backend.app.models.multi_agent import AgentType
from backend.app.security.sensitive_files import is_sensitive_path


class LearningSafetyDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    allowed: bool
    reason: str
    blocked_rules: List[str] = Field(default_factory=list)


class LearningSafetyGate:
    """Rejects recommendations that would weaken security or policy control."""

    _BLOCKED_PHRASES: tuple[re.Pattern, ...] = (
        re.compile(r"(?i)\bdisable\s+security(?:manager)?\b"),
        re.compile(r"(?i)\bbypass\s+approval\b"),
        re.compile(r"(?i)\bapprove\s+itself\b"),
        re.compile(r"(?i)\bself-?approve\b"),
        re.compile(r"(?i)\bignore\s+permissions\b"),
        re.compile(r"(?i)\boverride\s+rbac\b"),
        re.compile(r"(?i)\bmodify\s+securitymanager\b"),
        re.compile(r"(?i)\bmodify\s+toolregistry\b"),
        re.compile(r"(?i)\bshell\s*=\s*true\b"),
        re.compile(r"(?i)\bexecute\s+shell\b"),
        re.compile(r"(?i)\brun\s+shell\b"),
        re.compile(r"(?i)\bpath\s+traversal\b"),
        re.compile(r"(?i)\baccess\s+sensitive\s+file\b"),
        re.compile(r"(?i)\bread\s+private\s+key\b"),
        re.compile(r"(?i)\bread\s+\.env\b"),
        re.compile(r"(?i)\bchmod\s+777\b"),
        re.compile(r"(?i)\bsudo\b"),
        re.compile(r"(?i)\bescalate\s+privilege"),
    )

    _SAFE_STRATEGIES: frozenset[str] = frozenset(
        {
            "DIRECT",
            "SEQUENTIAL",
            "PARALLEL",
            "RESEARCH_THEN_CODE",
            "DEBUG_THEN_PATCH",
            "SECURITY_FIRST",
            "REVIEW_REQUIRED",
            "ITERATIVE_DEBUG",
        }
    )

    @classmethod
    def validate(
        cls,
        recommendation: LearningRecommendation,
        *,
        task_context: Optional[Dict[str, Any]] = None,
    ) -> LearningSafetyDecision:
        blocked_rules: List[str] = []

        text_blobs = [
            recommendation.recommendation,
            recommendation.expected_benefit,
            recommendation.blocked_reason or "",
            recommendation.recommendation_type,
            recommendation.target_strategy or "",
            recommendation.target_agent or "",
            recommendation.target_model or "",
            " ".join(f"{k}:{v}" for k, v in recommendation.resource_adjustment.items()),
            " ".join(str(v) for v in (task_context or {}).values() if v is not None),
        ]
        combined_text = "\n".join(str(text) for text in text_blobs if text)

        for pattern in cls._BLOCKED_PHRASES:
            if pattern.search(combined_text):
                blocked_rules.append(pattern.pattern)

        if recommendation.target_strategy and recommendation.target_strategy not in cls._SAFE_STRATEGIES:
            blocked_rules.append("unknown_strategy")

        if recommendation.target_agent:
            try:
                AgentType(recommendation.target_agent.lower())
            except ValueError:
                blocked_rules.append("unknown_agent")

        for key, value in recommendation.resource_adjustment.items():
            if isinstance(value, (int, float)) and value < 0:
                blocked_rules.append(f"negative_{key}")
            if key == "max_tokens" and isinstance(value, (int, float)) and value > settings.MAX_AGENT_TOKENS:
                blocked_rules.append("token_limit_exceeded")
            if key == "max_tool_calls" and isinstance(value, (int, float)) and value > settings.MAX_AGENT_TOOL_CALLS:
                blocked_rules.append("tool_call_limit_exceeded")
            if key == "max_execution_time" and isinstance(value, (int, float)) and value > settings.MAX_AGENT_RUNTIME:
                blocked_rules.append("runtime_limit_exceeded")
            if key == "max_retries" and isinstance(value, (int, float)) and value > settings.MAX_AGENT_RETRIES:
                blocked_rules.append("retry_limit_exceeded")
            if key == "max_depth" and isinstance(value, (int, float)) and value > settings.MAX_AGENT_DEPTH:
                blocked_rules.append("depth_limit_exceeded")

        for path in _iter_paths(task_context or {}):
            if is_sensitive_path(path):
                blocked_rules.append("sensitive_path_context")
                break

        if blocked_rules:
            reason = "Learning recommendation rejected by safety gate."
            return LearningSafetyDecision(allowed=False, reason=reason, blocked_rules=sorted(set(blocked_rules)))

        return LearningSafetyDecision(allowed=True, reason="Recommendation approved as advisory only.")

    @classmethod
    def filter_recommendations(
        cls,
        recommendations: Iterable[LearningRecommendation],
        *,
        task_context: Optional[Dict[str, Any]] = None,
    ) -> List[LearningRecommendation]:
        filtered: List[LearningRecommendation] = []
        for recommendation in recommendations:
            decision = cls.validate(recommendation, task_context=task_context)
            if decision.allowed:
                recommendation.safety_status = "approved"
                recommendation.blocked_reason = None
                filtered.append(recommendation)
            else:
                recommendation.safety_status = "rejected"
                recommendation.blocked_reason = decision.reason
        return filtered


def _iter_paths(context: Dict[str, Any]) -> Iterable[str]:
    for key, value in context.items():
        if isinstance(value, str) and ("path" in key.lower() or "file" in key.lower()):
            yield value
        elif isinstance(value, dict):
            yield from _iter_paths(value)
        elif isinstance(value, list):
            for item in value:
                if isinstance(item, str):
                    yield item
                elif isinstance(item, dict):
                    yield from _iter_paths(item)

