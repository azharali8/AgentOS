"""
AgentOS Phase 4 — Strongly typed data models for autonomous coding and debugging.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class TaskType(str, Enum):
    BUG_FIX = "bug_fix"
    TEST_FAILURE = "test_failure"
    REPOSITORY_ANALYSIS = "repository_analysis"
    CODE_EXPLANATION = "code_explanation"
    CODE_CHANGE = "code_change"
    UNKNOWN = "unknown"


class TaskClassification(BaseModel):
    """Result of task classification by TaskClassifierAgent."""
    task_type: TaskType = TaskType.UNKNOWN
    requires_tests: bool = True
    requires_code_change: bool = True
    risk_level: str = "HIGH"
    reasoning: str = ""
    target_files_hint: List[str] = Field(default_factory=list)


class FailureInfo(BaseModel):
    """Structured failure information extracted by FailureAnalyzerAgent."""
    test_name: str
    failure_type: str = "AssertionError"  # e.g., AssertionError, Exception, Timeout
    file_path: Optional[str] = None
    line_number: Optional[int] = None
    message: str = ""
    traceback: str = ""
    likely_files: List[str] = Field(default_factory=list)


class InvestigationResult(BaseModel):
    """Structured evidence gathered by CodeInvestigatorAgent."""
    affected_files: List[str] = Field(default_factory=list)
    relevant_symbols: List[Dict[str, Any]] = Field(default_factory=list)
    evidence: str = ""
    suspected_root_cause: str = ""
    confidence: float = Field(default=0.8, ge=0.0, le=1.0)
    recommended_change: str = ""


class DebugDiagnosis(BaseModel):
    """Root cause diagnosis and fix formulation by DebuggerAgent."""
    root_cause: str
    affected_files: List[str] = Field(default_factory=list)
    affected_symbols: List[str] = Field(default_factory=list)
    explanation: str
    recommended_fix: str
    confidence: float = Field(default=0.85, ge=0.0, le=1.0)
    risks: List[str] = Field(default_factory=list)


class JudgeVerdictType(str, Enum):
    SUCCESS = "SUCCESS"
    STILL_FAILING = "STILL_FAILING"
    REGRESSION = "REGRESSION"
    NEW_FAILURE = "NEW_FAILURE"
    INCONCLUSIVE = "INCONCLUSIVE"


class JudgeVerdict(BaseModel):
    """Verdict evaluated by ResultJudgeAgent after post-patch test execution."""
    verdict: JudgeVerdictType
    reasoning: str
    confidence: float = Field(default=0.9, ge=0.0, le=1.0)
    tests_passed: int = 0
    tests_failed: int = 0
    newly_failing_tests: List[str] = Field(default_factory=list)
    resolved_tests: List[str] = Field(default_factory=list)


class CodingReport(BaseModel):
    """Final engineering report summarizing the autonomous coding workflow."""
    task_id: str
    user_instruction: str
    task_type: str
    initial_failures_count: int = 0
    final_failures_count: int = 0
    root_cause: str = ""
    files_changed: List[str] = Field(default_factory=list)
    patch_summary: str = ""
    patch_hash: Optional[str] = None
    approval_status: str = ""
    debug_iterations: int = 0
    verdict: str = "SUCCESS"
    final_status: str = "COMPLETED"
    summary_text: str = ""
