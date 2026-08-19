"""
AgentOS Phase 4 — LangGraph State definition for the autonomous software engineering workflow.

Follows LangGraph TypedDict conventions.
Never stores entire source code or unfiltered repository dumps in state.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, TypedDict


class CodingAgentState(TypedDict, total=False):
    # Core identifiers
    task_id: str
    user_instruction: str
    thread_id: str

    # Classification
    classification: Dict[str, Any]  # TaskClassification serialized dict

    # Repository & test context
    repository_summary: Dict[str, Any]  # primary language, frameworks, file counts
    test_framework: str  # pytest, npm
    test_target: Optional[str]  # target path or test file

    # Test execution & analysis
    initial_test_result: Dict[str, Any]  # passed, exit_code, counts, failures summary
    failures: List[Dict[str, Any]]  # List of FailureInfo dicts
    investigation: Dict[str, Any]  # InvestigationResult dict
    diagnosis: Dict[str, Any]  # DebugDiagnosis dict

    # Patch & Approval
    proposed_patch: Dict[str, Any]  # Patch serialized dict
    patch_id: Optional[str]
    patch_hash: Optional[str]
    approval_id: Optional[str]
    approval_status: Optional[str]  # PENDING, APPROVED, REJECTED
    original_file_hashes: Dict[str, str]

    # Post-patch verification & judging
    latest_test_result: Dict[str, Any]
    judge_verdict: Dict[str, Any]  # JudgeVerdict dict

    # Iteration & bound controls
    iteration: int
    max_iterations: int
    debug_attempt: int
    max_debug_attempts: int

    # Rollback & final results
    rollback_required: bool
    rollback_applied: bool
    final_report: Dict[str, Any]  # CodingReport dict
    final_response: str
    status: str  # PLANNING, EXECUTING, WAITING_APPROVAL, COMPLETED, FAILED
    error: Optional[str]
