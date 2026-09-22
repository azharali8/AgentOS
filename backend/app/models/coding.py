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


class FailureClassification(str, Enum):
    APPLICATION_BUG = "APPLICATION_BUG"
    TEST_BUG = "TEST_BUG"
    CONFIGURATION_ERROR = "CONFIGURATION_ERROR"
    DEPENDENCY_ERROR = "DEPENDENCY_ERROR"
    ENVIRONMENT_ERROR = "ENVIRONMENT_ERROR"
    MODEL_AGENT_ERROR = "MODEL_AGENT_ERROR"
    UNKNOWN = "UNKNOWN"


class DiagnosedIssue(BaseModel):
    """Structured, evidence-grounded diagnosis for a single test failure or issue."""
    issue_number: int = 1
    title: str = "Test Failure"
    test_name: str = ""
    test_file: Optional[str] = None
    source_file: Optional[str] = None
    line: Optional[int] = None
    error_type: str = "AssertionError"
    message: str = ""
    stack_trace: str = ""
    explanation: str = ""
    likely_cause: str = ""
    suggested_fix: str = ""
    classification: FailureClassification = FailureClassification.APPLICATION_BUG
    confidence: float = Field(default=0.9, ge=0.0, le=1.0)
    source_snippet: Optional[str] = None


class StructuredTestReport(BaseModel):
    command: str = ""
    """Aggregated, user-friendly test result and diagnosis summary."""
    framework: str = "pytest"
    exit_code: int = 0
    passed: bool = True
    passed_count: int = 0
    failed_count: int = 0
    skipped_count: int = 0
    error_count: int = 0
    total_count: int = 0
    duration_seconds: float = 0.0
    issues: List[DiagnosedIssue] = Field(default_factory=list)
    raw_stdout: str = ""
    raw_stderr: str = ""

