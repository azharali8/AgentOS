"""
AgentOS Phase 8 - Continuous Learning Experience Models.

Typed, security-constrained models for recording execution experiences,
retrieving bounded evidence, and emitting advisory learning recommendations.
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


def _default_experience_id() -> str:
    return f"exp-{uuid.uuid4().hex[:12]}"


def _normalize_hash_source(value: str) -> str:
    return " ".join(value.strip().split()).lower()


def hash_task_description(text: str) -> str:
    """Return a deterministic SHA-256 hash for a redacted task description."""
    normalized = _normalize_hash_source(text)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


class ExecutionExperience(BaseModel):
    """Structured record of a single execution experience."""

    model_config = ConfigDict(extra="forbid")

    experience_id: str = Field(default_factory=_default_experience_id)
    task_id: str
    parent_task_id: Optional[str] = None
    task_type: str = "general"
    task_description_hash: str
    task_complexity: str = "medium"
    project_type: str = "python"
    framework: Optional[str] = None
    selected_strategy: str = "DIRECT"
    selected_model: Optional[str] = None
    selected_agents: List[str] = Field(default_factory=list)
    decomposition_summary: List[str] = Field(default_factory=list)
    plan_score: float = 0.0
    resource_budget: Dict[str, Any] = Field(default_factory=dict)
    execution_duration: float = 0.0
    tool_call_count: int = 0
    token_usage: int = 0
    success: bool = False
    failure_type: Optional[str] = None
    failure_pattern: Optional[str] = None
    regression_detected: bool = False
    approval_required: bool = False
    approval_outcome: Optional[str] = None
    security_events: List[str] = Field(default_factory=list)
    evaluation_score: float = 0.0
    final_outcome: str = "UNKNOWN"
    evidence_ids: List[str] = Field(default_factory=list)
    task_summary: Optional[str] = None
    learning_metadata: Dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator("task_description_hash")
    @classmethod
    def _validate_hash(cls, value: str) -> str:
        cleaned = value.strip().lower()
        if len(cleaned) != 64 or any(ch not in "0123456789abcdef" for ch in cleaned):
            raise ValueError("task_description_hash must be a 64-character lowercase hex digest")
        return cleaned

    @field_validator("selected_agents", "decomposition_summary", "security_events", "evidence_ids", mode="before")
    @classmethod
    def _ensure_lists(cls, value: Any) -> List[Any]:
        if value is None:
            return []
        if isinstance(value, list):
            return value
        if isinstance(value, tuple):
            return list(value)
        return [value]


class RetrievedExperience(BaseModel):
    """Bounded retrieval result with relevance scoring."""

    model_config = ConfigDict(extra="forbid")

    experience: ExecutionExperience
    relevance_score: float = Field(default=0.0, ge=0.0, le=1.0)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    matched_signals: List[str] = Field(default_factory=list)
    rationale: str = ""


class LearningRecommendation(BaseModel):
    """Advisory learning recommendation validated by the safety gate."""

    model_config = ConfigDict(extra="forbid")

    recommendation_type: str
    recommendation: str
    evidence_count: int = 0
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    expected_benefit: str = ""
    supporting_experience_ids: List[str] = Field(default_factory=list)
    target_strategy: Optional[str] = None
    target_agent: Optional[str] = None
    target_model: Optional[str] = None
    resource_adjustment: Dict[str, Any] = Field(default_factory=dict)
    safety_status: str = "approved"
    blocked_reason: Optional[str] = None


class LearningAnalysis(BaseModel):
    """Structured learning summary for a task or execution family."""

    model_config = ConfigDict(extra="forbid")

    task_id: str
    task_type: str = "general"
    retrieved_count: int = 0
    success_rate: float = Field(default=0.0, ge=0.0, le=1.0)
    failure_rate: float = Field(default=0.0, ge=0.0, le=1.0)
    average_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    recommendations: List[LearningRecommendation] = Field(default_factory=list)
    retrieved_experiences: List[RetrievedExperience] = Field(default_factory=list)
    strategy_recommendation: Optional[str] = None
    agent_recommendations: List[LearningRecommendation] = Field(default_factory=list)
    model_recommendations: List[LearningRecommendation] = Field(default_factory=list)
    failure_recommendations: List[LearningRecommendation] = Field(default_factory=list)
    resource_recommendations: List[LearningRecommendation] = Field(default_factory=list)
    summary: str = ""
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

