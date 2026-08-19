"""
AgentOS Phase 7 — Experience, Learning, Profiling & Consensus Data Models.

Provides strongly typed Pydantic models for:
- Task & Agent Experience recording
- Failure pattern classification
- Agent performance profiling
- Strategy recommendations
- Multi-agent consensus synthesis
- Self-reflection results
- Bounded adaptive routing insights
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from backend.app.models.multi_agent import AgentType


class FailureCategory(str, Enum):
    TEST_FAILURE = "TEST_FAILURE"
    PATCH_FAILURE = "PATCH_FAILURE"
    TOOL_FAILURE = "TOOL_FAILURE"
    SECURITY_DENIAL = "SECURITY_DENIAL"
    TIMEOUT = "TIMEOUT"
    DEPENDENCY_ERROR = "DEPENDENCY_ERROR"
    ENVIRONMENT_ERROR = "ENVIRONMENT_ERROR"
    REGRESSION = "REGRESSION"
    AGENT_FAILURE = "AGENT_FAILURE"
    PLANNING_FAILURE = "PLANNING_FAILURE"
    ROUTING_FAILURE = "ROUTING_FAILURE"
    UNKNOWN = "UNKNOWN"


class ExperienceRecord(BaseModel):
    experience_id: str
    task_id: str
    task_type: str = "bug_fix"
    task_classification: str = "bug_fix"
    project_type: str = "python"
    instruction_summary: str = ""
    agents_used: List[str] = Field(default_factory=list)
    decomposition_summary: List[str] = Field(default_factory=list)
    strategy: str = "RESEARCH_DEBUG_CODE_REVIEW"
    tools_used: List[str] = Field(default_factory=list)
    outcome: str = "SUCCESS"
    success: bool = True
    failure_category: Optional[FailureCategory] = None
    iterations: int = 1
    retries: int = 0
    duration_seconds: float = 0.0
    token_usage: int = 0
    estimated_cost: float = 0.0
    approval_required: bool = False
    regression_detected: bool = False
    lessons_learned: List[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class AgentPerformanceProfile(BaseModel):
    agent_type: AgentType
    task_count: int = 0
    successful_tasks: int = 0
    failed_tasks: int = 0
    success_rate: float = 1.0
    avg_runtime_seconds: float = 0.0
    avg_tokens: float = 0.0
    avg_tool_calls: float = 0.0
    retry_rate: float = 0.0
    timeout_rate: float = 0.0
    regression_rate: float = 0.0
    task_type_success: Dict[str, float] = Field(default_factory=dict)
    confidence_score: float = 0.95


class RoutingDecision(BaseModel):
    decision_id: str
    task_id: str
    subtask_id: str
    selected_agent: AgentType
    candidate_scores: Dict[str, float] = Field(default_factory=dict)
    reasoning: str
    estimated_cost: float = 0.0
    confidence: float = 0.9


class ReflectionResult(BaseModel):
    task_id: str
    overall_quality: float = Field(default=0.9, ge=0.0, le=1.0)
    planning_quality: float = Field(default=0.9, ge=0.0, le=1.0)
    routing_quality: float = Field(default=0.9, ge=0.0, le=1.0)
    diagnosis_quality: float = Field(default=0.9, ge=0.0, le=1.0)
    execution_efficiency: float = Field(default=0.85, ge=0.0, le=1.0)
    lessons: List[str] = Field(default_factory=list)
    recommended_strategy: str = "RESEARCH_DEBUG_CODE_REVIEW"
    avoidable_steps: List[str] = Field(default_factory=list)
    reflection_timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ConsensusResult(BaseModel):
    task_id: str
    decision: str
    confidence: float = 0.95
    agreement_score: float = 1.0
    participating_agents: List[AgentType] = Field(default_factory=list)
    dissenting_opinions: List[str] = Field(default_factory=list)
    evidence: List[Dict[str, Any]] = Field(default_factory=list)
    security_approved: bool = True
