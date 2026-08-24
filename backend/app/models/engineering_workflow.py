"""
AgentOS Phase 12 — Structured Inter-Agent Pydantic Schemas.

Defines typed, validated data models exchanged between specialized engineering agents:
- CodingAgent (CodeChangesPayload)
- DebuggerAgent (DiagnosisReport)
- TestingAgent (TestExecutionReport)
- ReviewerAgent (ReviewVerdictPayload)
- DevOpsAgent (DevOpsAnalysisReport)
- DataEngineerAgent (DataEngineeringReport)
- SupervisorAgent (ReplanningDecision, EngineeringWorkflowSummary)
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class CodeChangesPayload(BaseModel):
    """Structured output from CodingAgent upon patch generation or code modification."""
    files_modified: List[str] = Field(default_factory=list, description="List of workspace-relative paths modified")
    patch_hash: str = Field(default="", description="Cryptographic SHA-256 hash of the unified patch")
    diff_content: str = Field(default="", description="Unified diff text")
    hunks_count: int = Field(default=0, description="Total number of diff hunks")
    security_risk: str = Field(default="LOW", description="Risk classification: LOW, MEDIUM, HIGH, CRITICAL")
    applied: bool = Field(default=False, description="Whether the patch has been written to the workspace")
    validation_errors: List[str] = Field(default_factory=list, description="Syntax or AST validation errors")


class DiagnosisReport(BaseModel):
    """Structured output from DebuggerAgent diagnosing failures or bugs."""
    symptoms: List[str] = Field(default_factory=list, description="Observed error symptoms or failing test outputs")
    suspected_files: List[str] = Field(default_factory=list, description="Candidate files suspected of causing the defect")
    root_cause: str = Field(default="", description="Detailed root cause explanation")
    suggested_fix: str = Field(default="", description="High-level fix strategy for the CodingAgent")
    confidence_score: float = Field(default=1.0, ge=0.0, le=1.0, description="Confidence in the diagnosis")


class TestCaseResult(BaseModel):
    """Single test execution details."""
    name: str
    passed: bool
    duration_seconds: float = 0.0
    failure_message: Optional[str] = None


class TestExecutionReport(BaseModel):
    """Structured output from TestingAgent executing test suites."""
    command: str = Field(default="", description="Actual executed test command")
    framework: str = Field(default="pytest", description="Test framework used (pytest, npm, etc.)")
    exit_code: int = Field(default=0, description="Process exit code")
    duration_seconds: float = Field(default=0.0, description="Execution duration in seconds")
    total_tests: int = Field(default=0, description="Total number of tests run")
    passed_count: int = Field(default=0, description="Count of passing tests")
    failed_count: int = Field(default=0, description="Count of failing tests")
    passed: bool = Field(default=True, description="True if all tests passed and exit_code == 0")
    test_cases: List[TestCaseResult] = Field(default_factory=list, description="Detailed per-case results")
    stdout_redacted: str = Field(default="", description="Sanitized stdout output")
    stderr_redacted: str = Field(default="", description="Sanitized stderr output")


class ReviewVerdictPayload(BaseModel):
    """Structured output from ReviewerAgent reviewing patches and test outputs."""
    approved: bool = Field(default=True, description="Whether the reviewer approves merging/finalizing the change")
    verdict: str = Field(default="APPROVE", description="APPROVE, REVISE, or REJECT")
    quality_score: float = Field(default=1.0, ge=0.0, le=1.0, description="Code quality rating (0.0 to 1.0)")
    security_concerns: List[str] = Field(default_factory=list, description="Identified security or policy risks")
    recommendations: List[str] = Field(default_factory=list, description="Actionable code improvements or cleanups")
    summary: str = Field(default="", description="High-level review summary")


class DevOpsAnalysisReport(BaseModel):
    """Structured output from DevOpsAgent."""
    ci_cd_configured: bool = Field(default=False, description="Whether CI/CD pipelines are detected")
    docker_configured: bool = Field(default=False, description="Whether Docker configurations are detected")
    detected_configs: List[str] = Field(default_factory=list, description="Discovered CI/CD and infrastructure files")
    security_findings: List[str] = Field(default_factory=list, description="Security findings in infrastructure files")
    recommendations: List[str] = Field(default_factory=list, description="Infrastructure recommendations")


class DataEngineeringReport(BaseModel):
    """Structured output from DataEngineerAgent."""
    datasets_analyzed: List[str] = Field(default_factory=list, description="Paths to datasets analyzed")
    row_counts: Dict[str, int] = Field(default_factory=dict, description="Dataset row counts")
    null_counts: Dict[str, int] = Field(default_factory=dict, description="Detected missing values")
    data_types: Dict[str, Dict[str, str]] = Field(default_factory=dict, description="Column data types")
    cleaning_operations: List[str] = Field(default_factory=list, description="Cleaning transformations applied")
    summary: str = Field(default="", description="EDA summary report")


class ReplanningDecision(BaseModel):
    """Structured record of a failure recovery or replanning action."""
    trigger_event: str = Field(..., description="Event that triggered replanning (e.g. TEST_FAILURE, TOOL_ERROR)")
    failed_subtask_id: str = Field(..., description="ID of the subtask that failed")
    reason: str = Field(..., description="Diagnostic rationale for the decision")
    strategy: str = Field(default="RETRY", description="RETRY, REROUTE, REPLAN, or ABORT")
    assigned_agent: Optional[str] = Field(default=None, description="Newly assigned agent if rerouting")
    recovery_instructions: str = Field(default="", description="Specific guidance passed to recovery agent")


class EngineeringWorkflowSummary(BaseModel):
    """Comprehensive final engineering artifact generated upon task completion."""
    task_id: str
    instruction: str
    status: str
    duration_seconds: float = 0.0
    files_inspected: List[str] = Field(default_factory=list)
    files_modified: List[str] = Field(default_factory=list)
    patch_hashes: List[str] = Field(default_factory=list)
    tests_summary: Optional[Dict[str, Any]] = None
    review_verdict: Optional[str] = None
    approvals_count: int = 0
    replan_count: int = 0
    artifacts: Dict[str, Any] = Field(default_factory=dict)
