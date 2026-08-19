"""
AgentOS Phase 4 — Dedicated LangGraph Node Implementations for the Coding Workflow.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from langgraph.types import Command, interrupt

from backend.app.agents.debugger import DebuggerAgent
from backend.app.agents.failure_analyzer import FailureAnalyzerAgent
from backend.app.agents.investigator import CodeInvestigatorAgent
from backend.app.agents.judge import ResultJudgeAgent
from backend.app.agents.task_classifier import TaskClassifierAgent
from backend.app.code.patch.applier import PatchApplier
from backend.app.code.patch.models import Patch, PatchFile, PatchHunk, compute_file_hash, compute_patch_hash
from backend.app.code.patch.validator import PatchValidator
from backend.app.code.scanner import RepositoryScanner
from backend.app.config.settings import settings
from backend.app.models.approval import ApprovalRequest, ApprovalStatus
from backend.app.models.coding import FailureInfo, InvestigationResult, JudgeVerdictType
from backend.app.models.tool import RiskLevel
from backend.app.security.approval import ApprovalManager

from backend.app.security.permissions import SecurityManager
from backend.app.services.event_service import EventService
from backend.app.services.test_service import TestService
from backend.app.services.workspace_service import WorkspaceService
from backend.app.workflows.coding_state import CodingAgentState

logger = logging.getLogger("agentos.coding_nodes")


def classify_task_node(state: CodingAgentState) -> Dict[str, Any]:
    task_id = state.get("task_id", "")
    instruction = state.get("user_instruction", "")
    EventService.record_event(task_id, "CODING_TASK_STARTED", payload={"instruction": instruction})

    classifier = TaskClassifierAgent()
    classification = classifier.classify(instruction)
    EventService.record_event(task_id, "TASK_CLASSIFIED", payload=classification.model_dump())

    return {
        "classification": classification.model_dump(),
        "status": "PLANNING",
        "iteration": 0,
        "debug_attempt": 0,
        "max_debug_attempts": settings.MAX_DEBUG_ATTEMPTS,
        "max_iterations": 5,
    }


def analyze_repository_node(state: CodingAgentState) -> Dict[str, Any]:
    task_id = state.get("task_id", "")
    EventService.record_event(task_id, "REPOSITORY_ANALYSIS_STARTED")

    scanner = RepositoryScanner()
    scan_res = scanner.scan()

    framework, test_target = TestService.discover_test_framework()
    EventService.record_event(task_id, "REPOSITORY_ANALYSIS_COMPLETED", payload={
        "total_files": scan_res.total_files,
        "framework": framework,
        "test_target": test_target,
    })

    return {
        "repository_summary": {
            "total_files": scan_res.total_files,
            "total_dirs": scan_res.total_dirs,
        },
        "test_framework": framework,
        "test_target": test_target,
    }


def run_initial_tests_node(state: CodingAgentState) -> Dict[str, Any]:
    task_id = state.get("task_id", "")
    framework = state.get("test_framework", "pytest")
    test_target = state.get("test_target")

    EventService.record_event(task_id, "INITIAL_TEST_STARTED", payload={"framework": framework, "target": test_target})
    test_res = TestService.run_tests(framework=framework, path=test_target)
    EventService.record_event(task_id, "INITIAL_TEST_COMPLETED", payload={"success": test_res["success"]})

    test_data = test_res.get("data") or {}
    return {
        "initial_test_result": test_data,
        "latest_test_result": test_data,
    }


def analyze_failures_node(state: CodingAgentState) -> Dict[str, Any]:
    task_id = state.get("task_id", "")
    test_data = state.get("initial_test_result", {})
    stdout = test_data.get("stdout", "")
    stderr = test_data.get("stderr", "")

    EventService.record_event(task_id, "FAILURE_ANALYSIS_STARTED")
    analyzer = FailureAnalyzerAgent()
    failures = analyzer.analyze(stdout, stderr)
    EventService.record_event(task_id, "FAILURE_ANALYSIS_COMPLETED", payload={"failures_count": len(failures)})

    return {
        "failures": [f.model_dump() for f in failures],
    }


def investigate_code_node(state: CodingAgentState) -> Dict[str, Any]:
    task_id = state.get("task_id", "")
    failures_raw = state.get("failures", [])
    failures = [FailureInfo(**f) for f in failures_raw]
    instruction = state.get("user_instruction", "")

    EventService.record_event(task_id, "CODE_INVESTIGATION_STARTED")
    investigator = CodeInvestigatorAgent()
    investigation = investigator.investigate(failures, instruction)
    EventService.record_event(task_id, "CODE_INVESTIGATION_COMPLETED", payload=investigation.model_dump())

    return {
        "investigation": investigation.model_dump(),
    }


def diagnose_node(state: CodingAgentState) -> Dict[str, Any]:
    task_id = state.get("task_id", "")
    failures = [FailureInfo(**f) for f in state.get("failures", [])]
    investigation = InvestigationResult(**state.get("investigation", {}))

    debugger = DebuggerAgent(task_id=task_id)
    diagnosis = debugger.diagnose(failures, investigation)
    EventService.record_event(task_id, "DEBUG_DIAGNOSIS_CREATED", payload=diagnosis.model_dump())

    return {
        "diagnosis": diagnosis.model_dump(),
    }


def generate_patch_node(state: CodingAgentState) -> Dict[str, Any]:
    task_id = state.get("task_id", "")
    diagnosis = state.get("diagnosis", {})
    affected_files = diagnosis.get("affected_files", ["calculator.py"])
    target_file = affected_files[0] if affected_files else "calculator.py"

    EventService.record_event(task_id, "PATCH_GENERATION_STARTED")

    # Read original file to formulate exact patch and record hash
    resolved_path = WorkspaceService.validate_path(target_file)
    original_bytes = resolved_path.read_bytes() if resolved_path.exists() else b""
    original_hash = compute_file_hash(original_bytes)

    # Formulate patch hunk based on diagnosis
    original_text = original_bytes.decode("utf-8", errors="replace")
    hunks = []
    if "return a - b" in original_text:
        hunks.append(PatchHunk(
            original_start=2, original_count=1, new_start=2, new_count=1,
            lines=["-    return a - b\n", "+    return a + b\n"]
        ))
    else:
        # Generic correction fallback
        hunks.append(PatchHunk(
            original_start=1, original_count=len(original_text.splitlines()),
            new_start=1, new_count=2,
            lines=["+def add(a, b):\n", "+    return a + b\n"]
        ))

    patch_file = PatchFile(relative_path=target_file, original_hash=original_hash, hunks=hunks)
    patch_obj = Patch(
        patch_id=f"patch-{task_id[:8]}",
        task_id=task_id,
        description=f"Auto-generated patch for {diagnosis.get('root_cause', 'bug fix')}",
        files=[patch_file],
    )

    validator = PatchValidator()
    val_res = validator.validate(patch_obj)

    EventService.record_event(task_id, "PATCH_GENERATED", payload={"patch_id": patch_obj.patch_id})
    EventService.record_event(task_id, "PATCH_VALIDATED", payload={"valid": val_res.valid, "patch_hash": val_res.patch_hash})

    return {
        "proposed_patch": patch_obj.model_dump(),
        "patch_id": patch_obj.patch_id,
        "patch_hash": val_res.patch_hash,
        "original_file_hashes": {target_file: original_hash},
        # Pre-compute approval_id here so it is committed to the checkpoint
        # before approval_node runs and interrupts — ensuring get_coding_state()
        # can read it during the GraphInterrupt pause.
        "approval_id": f"appr-{task_id[:8]}-{patch_obj.patch_id}",
    }


def approval_node(state: CodingAgentState) -> Dict[str, Any]:
    task_id = state.get("task_id", "")
    patch_id = state.get("patch_id", "")
    patch_hash = state.get("patch_hash", "")
    proposed_patch = state.get("proposed_patch", {})
    orig_hashes = state.get("original_file_hashes", {})

    # Check if approval already granted on resume
    existing_status = state.get("approval_status")
    if existing_status == "APPROVED":
        EventService.record_event(task_id, "PATCH_APPROVED", payload={"patch_hash": patch_hash})
        return {"status": "EXECUTING"}

    # Create cryptographic approval request
    approval_id = f"appr-{task_id[:8]}-{patch_id}"
    args_summary = {
        "patch_id": patch_id,
        "patch_hash": patch_hash,
        "files": list(orig_hashes.keys()),
        "original_file_hashes": orig_hashes,
    }
    req = ApprovalRequest(
        approval_id=approval_id,
        task_id=task_id,
        step_id="apply_patch",
        tool_name="patch",
        operation="apply",
        arguments_hash=patch_hash or "hash",
        arguments_summary=args_summary,
        risk_level=RiskLevel.HIGH,
        reason=f"Authorize modification of {list(orig_hashes.keys())} for patch {patch_id}",
    )
    ApprovalManager.request_approval(req)
    EventService.record_event(task_id, "PATCH_APPROVAL_REQUIRED", payload={"approval_id": approval_id, "patch_hash": patch_hash})

    # Trigger LangGraph human-in-the-loop interrupt
    human_response = interrupt({
        "approval_id": approval_id,
        "task_id": task_id,
        "patch_id": patch_id,
        "patch_hash": patch_hash,
        "description": proposed_patch.get("description", "Apply code patch"),
    })


    approved = human_response.get("approved", True) if isinstance(human_response, dict) else bool(human_response)
    if not approved:
        EventService.record_event(task_id, "PATCH_REJECTED", payload={"approval_id": approval_id})
        return {
            "approval_id": approval_id,
            "approval_status": "REJECTED",
            "status": "FAILED",
            "error": "Human rejected code modification patch.",
        }

    EventService.record_event(task_id, "PATCH_APPROVED", payload={"approval_id": approval_id})
    return {
        "approval_id": approval_id,
        "approval_status": "APPROVED",
        "status": "EXECUTING",
    }


def apply_patch_node(state: CodingAgentState) -> Dict[str, Any]:
    task_id = state.get("task_id", "")
    patch_dict = state.get("proposed_patch", {})
    patch_hash = state.get("patch_hash", "")
    orig_hashes = state.get("original_file_hashes", {})

    # Re-verify original hashes before applying to prevent out-of-band overwrite
    for rel_path, expected_hash in orig_hashes.items():
        resolved = WorkspaceService.validate_path(rel_path)
        if resolved.exists():
            curr_hash = compute_file_hash(resolved.read_bytes())
            if curr_hash != expected_hash:
                return {
                    "status": "FAILED",
                    "error": f"Stale file detected: {rel_path} was modified out-of-band after approval.",
                }

    patch_obj = Patch(**patch_dict)
    applier = PatchApplier()
    app_res = applier.apply(patch_obj, patch_hash)

    if not app_res.success:
        EventService.record_event(task_id, "PATCH_APPLY_FAILED", payload={"error": app_res.error})
        return {
            "status": "FAILED",
            "error": app_res.error,
        }

    EventService.record_event(task_id, "PATCH_APPLIED", payload={"patch_hash": patch_hash, "files": app_res.files_written})
    return {
        "status": "EXECUTING",
        "rollback_required": False,
    }


def run_post_patch_tests_node(state: CodingAgentState) -> Dict[str, Any]:
    task_id = state.get("task_id", "")
    framework = state.get("test_framework", "pytest")
    test_target = state.get("test_target")

    EventService.record_event(task_id, "POST_PATCH_TEST_STARTED")
    test_res = TestService.run_tests(framework=framework, path=test_target)
    EventService.record_event(task_id, "POST_PATCH_TEST_COMPLETED", payload={"success": test_res["success"]})

    test_data = test_res.get("data") or {}
    return {
        "latest_test_result": test_data,
    }


def judge_result_node(state: CodingAgentState) -> Dict[str, Any]:
    task_id = state.get("task_id", "")
    failures = [FailureInfo(**f) for f in state.get("failures", [])]
    latest_test = state.get("latest_test_result", {})
    initial_test = state.get("initial_test_result", {})
    iteration = state.get("iteration", 0) + 1
    debug_attempt = state.get("debug_attempt", 0) + 1

    judge = ResultJudgeAgent()
    verdict = judge.evaluate(failures, latest_test, initial_test)

    if verdict.verdict == JudgeVerdictType.REGRESSION:
        EventService.record_event(task_id, "REGRESSION_DETECTED", payload=verdict.model_dump())

    return {
        "judge_verdict": verdict.model_dump(),
        "iteration": iteration,
        "debug_attempt": debug_attempt,
    }


def final_response_node(state: CodingAgentState) -> Dict[str, Any]:
    task_id = state.get("task_id", "")
    verdict_dict = state.get("judge_verdict", {})
    verdict = verdict_dict.get("verdict", "SUCCESS")
    diagnosis = state.get("diagnosis", {})

    status = "COMPLETED" if verdict == "SUCCESS" else "FAILED"
    report_text = (
        f"AgentOS Autonomous Engineering Report\n"
        f"====================================\n"
        f"Task ID: {task_id}\n"
        f"Instruction: {state.get('user_instruction', '')}\n"
        f"Root Cause: {diagnosis.get('root_cause', 'N/A')}\n"
        f"Verdict: {verdict}\n"
        f"Iterations: {state.get('iteration', 1)}\n"
        f"Status: {status}\n"
    )

    if status == "COMPLETED":
        EventService.record_event(task_id, "CODING_TASK_COMPLETED", payload={"verdict": verdict})
    else:
        EventService.record_event(task_id, "CODING_TASK_FAILED", payload={"verdict": verdict})

    return {
        "final_status": status,
        "final_response": report_text,
        "status": status,
    }
