"""
AgentOS Phase 5, 12 & 13 — Multi-Agent LangGraph Nodes.

Implements sequential and parallel workflow nodes:
- supervisor_plan
- decompose_task
- parallel_execution
- adaptive_replan
- security_review
- human_approval (real cryptographic binding + application)
- merge_results
- final_response
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from langgraph.types import interrupt

from backend.app.agents.supervisor import SupervisorAgent
from backend.app.code.patch.models import Patch
from backend.app.config.settings import settings
from backend.app.models.approval import ApprovalRequest, ApprovalStatus
from backend.app.models.multi_agent import AgentResult, AgentStatus, AgentType, SubTask
from backend.app.models.tool import RiskLevel
from backend.app.security.approval import ApprovalManager
from backend.app.services.agent_budget import AgentBudgetTracker
from backend.app.services.artifact_service import ArtifactService, ArtifactType
from backend.app.services.event_service import EventService
from backend.app.services.task_runtime import TaskRuntime
from backend.app.workflows.multi_agent_state import MultiAgentState

logger = logging.getLogger("agentos.multi_agent_nodes")


def supervisor_plan_node(state: MultiAgentState) -> Dict[str, Any]:
    """Initialize multi-agent coordination task and budget."""
    task_id = state.get("task_id", "task-1")
    instruction = state.get("user_instruction", "")

    EventService.record_event(task_id, "TASK_CREATED", payload={"instruction": instruction})
    EventService.record_event(task_id, "PLAN_CREATED", payload={"instruction": instruction})
    AgentBudgetTracker.initialize_task(task_id)

    return {
        "status": "PLANNING",
        "iteration": 0,
        "completed_subtask_ids": [],
        "subtask_results": {},
    }


def decompose_task_node(state: MultiAgentState) -> Dict[str, Any]:
    """Decompose user request into structured SubTask DAG with TaskClassifier and ContextEngine."""
    task_id = state.get("task_id", "task-1")
    instruction = state.get("user_instruction", "")

    supervisor = SupervisorAgent()
    subtasks = supervisor.plan_and_decompose(instruction, task_id=task_id)

    for st in subtasks:
        EventService.record_event(task_id, "SUBTASK_CREATED", payload=st.model_dump())
        EventService.record_event(task_id, "AGENT_SELECTED", payload={"subtask_id": st.subtask_id, "agent": st.assigned_agent.value})

    # Pre-check if any coding subtask requires approval
    has_coding = any(st.assigned_agent == AgentType.CODING for st in subtasks)
    approval_id = f"appr-{task_id[:8]}-multi" if has_coding else None

    return {
        "subtasks": [st.model_dump() for st in subtasks],
        "approval_required": has_coding,
        "approval_id": approval_id,
        "status": "EXECUTING",
    }


def parallel_execution_node(state: MultiAgentState) -> Dict[str, Any]:
    """Execute ready subtasks with pause-barrier checks and failure handling."""
    task_id = state.get("task_id", "task-1")
    from backend.app.services.task_service import TaskService
    from backend.app.models.task import TaskStatus
    task = TaskService.get_task(task_id)
    if task and task.status in (TaskStatus.CANCELLED, TaskStatus.CANCELLING):
        return {"status": "CANCELLED"}
    if TaskRuntime.is_paused(task_id):
        logger.info("Task %s execution node halting at pause barrier.", task_id)
        return {"status": "PAUSED"}

    subtasks_raw = state.get("subtasks", [])
    completed_ids = set(state.get("completed_subtask_ids", []))
    subtask_results = dict(state.get("subtask_results", {}))

    supervisor = SupervisorAgent()

    # Find runnable subtasks (dependencies met)
    runnable: List[SubTask] = []
    for st_dict in subtasks_raw:
        st = SubTask(**st_dict)
        if st.subtask_id in completed_ids:
            continue
        if all(dep in completed_ids for dep in st.dependencies):
            st.input_data = {**st.input_data, "user_instruction": state.get("user_instruction", ""),
                             "changed_files": list(dict.fromkeys(f for r in subtask_results.values()
                                 if r.get("agent_type") == AgentType.CODING.value for f in r.get("files_modified", []))),
                             **{dep: subtask_results[dep] for dep in st.dependencies if dep in subtask_results}}
            runnable.append(st)

    if not runnable:
        if len(completed_ids) < len(subtasks_raw):
            return {"status": "FAILED", "error": "No runnable subtasks; unresolved dependencies"}
        return {"status": "EXECUTING"}

    # A coding proposal must be approved/applied before another batch can read it.
    # Serialize coding proposals so separate patches cannot share stale originals.
    coding = next((st for st in runnable if st.assigned_agent == AgentType.CODING), None)
    if coding:
        runnable = [coding]

    # Execute runnable batch
    batch_results = supervisor.executor.execute_batch(
        subtasks=runnable,
        runner_fn=supervisor.execute_subtask,
        task_id=task_id,
    )

    pending_coding_id = None
    fatal_error = None
    for s_id, res in batch_results.items():
        completed_ids.add(s_id)
        subtask_results[s_id] = res.model_dump()
        EventService.record_event(task_id, "SUBTASK_FAILED" if res.status == AgentStatus.FAILED else "SUBTASK_COMPLETED", payload=res.model_dump())

        if res.agent_type == AgentType.CODING and res.evidence.get("patch"):
            if res.status == AgentStatus.COMPLETED:
                pending_coding_id = s_id
            patch_data = res.evidence.get("patch", {})
            EventService.record_event(
                task_id,
                "PATCH_CREATED",
                payload={"patch_id": patch_data.get("patch_id"), "files": res.files_modified, "patch_hash": res.evidence.get("patch_hash")},
            )
        elif res.agent_type == AgentType.TESTING:
            EventService.record_event(
                task_id,
                "TEST_COMPLETED",
                payload={"report": res.evidence.get("structured_report", {})},
            )
        if res.status in (AgentStatus.FAILED, AgentStatus.TIMEOUT, AgentStatus.CANCELLED):
            fatal_error = res.error or res.summary

    recovery = {}
    failed_tests = [r for r in batch_results.values() if r.agent_type == AgentType.TESTING and r.status == AgentStatus.FAILED]
    iteration = state.get("iteration", 0)
    if (failed_tests and len(failed_tests) == len([r for r in batch_results.values() if r.status != AgentStatus.COMPLETED])
            and state.get("applied_coding_ids") and iteration < settings.MAX_DEBUG_ATTEMPTS
            and len(subtasks_raw) + 3 <= settings.MAX_SUBTASKS):
        failure = failed_tests[0]
        original = next(SubTask(**s) for s in subtasks_raw if s["subtask_id"] == failure.subtask_id)
        decision = supervisor.handle_subtask_failure(original, failure, task_id)
        prefix = f"recovery-{iteration + 1}"
        targets = list(dict.fromkeys(
            f for r in subtask_results.values() if r.get("agent_type") == AgentType.CODING.value
            for f in r.get("files_modified", [])
        ))
        diagnosis = SubTask(task_id=task_id, subtask_id=f"{prefix}-diagnose", assigned_agent=AgentType.DEBUGGER,
                            description=decision.recovery_instructions, dependencies=[failure.subtask_id], target_files=targets)
        fix = SubTask(task_id=task_id, subtask_id=f"{prefix}-fix", assigned_agent=AgentType.CODING,
                      description=f"Fix the observed test failure while fulfilling: {state.get('user_instruction', '')}",
                      dependencies=[diagnosis.subtask_id], target_files=targets)
        retest = SubTask(task_id=task_id, subtask_id=f"{prefix}-test", assigned_agent=AgentType.TESTING,
                         description="Run tests again after the approved fix", dependencies=[fix.subtask_id])
        updated_subtasks = [dict(s) for s in subtasks_raw]
        for s in updated_subtasks:
            if s["subtask_id"] not in completed_ids:
                s["dependencies"] = [retest.subtask_id if d == failure.subtask_id else d for d in s.get("dependencies", [])]
        additions = [diagnosis, fix, retest]
        for st in additions:
            EventService.record_event(task_id, "SUBTASK_CREATED", payload=st.model_dump())
        recovery = {"subtasks": updated_subtasks + [st.model_dump() for st in additions], "iteration": iteration + 1,
                    "recovery_replacements": {**state.get("recovery_replacements", {}), failure.subtask_id: retest.subtask_id}}
        fatal_error = None

    return {
        **recovery,
        "completed_subtask_ids": list(completed_ids),
        "subtask_results": subtask_results,
        "status": "FAILED" if fatal_error else "EXECUTING",
        "error": fatal_error,
        "pending_coding_id": pending_coding_id,
        "approval_id": f"appr-{task_id}-{pending_coding_id}-{state.get('iteration', 0)}" if pending_coding_id else state.get("approval_id"),
    }


def human_approval_node(state: MultiAgentState) -> Dict[str, Any]:
    """Human-in-the-loop gate binding SHA-256 patch hash."""
    task_id = state.get("task_id", "task-1")
    subtask_results = state.get("subtask_results", {})

    coding_res_dict = subtask_results.get(state.get("pending_coding_id")) or next(
        (r for r in subtask_results.values() if r.get("agent_type") == AgentType.CODING.value),
        None,
    )

    patch_hash = ""
    patch_dict = None
    if coding_res_dict and coding_res_dict.get("evidence"):
        patch_hash = coding_res_dict["evidence"].get("patch_hash", "")
        patch_dict = coding_res_dict["evidence"].get("patch")

    approval_id = state.get("approval_id") or f"appr-{task_id[:8]}"
    appr_req = ApprovalRequest(
        approval_id=approval_id,
        task_id=task_id,
        step_id="multi-agent-coding",
        tool_name="patch.apply",
        operation="apply",
        arguments_hash=patch_hash or "empty_hash",
        arguments_summary={"patch_hash": patch_hash, "files": coding_res_dict.get("files_modified", []) if coding_res_dict else []},
        risk_level=RiskLevel.HIGH,
        reason="Human approval required to apply verified code mutations",
        status=ApprovalStatus.PENDING,
    )
    ApprovalManager.request_approval(appr_req)
    EventService.record_event(
        task_id,
        "APPROVAL_REQUIRED",
        payload={"approval_id": approval_id, "patch_hash": patch_hash},
    )

    # LangGraph interrupt
    approval_result = interrupt({
        "approval_id": approval_id,
        "task_id": task_id,
        "patch_hash": patch_hash,
        "message": "Human approval required to apply code changes to workspace.",
    })

    approved = approval_result.get("approved", False) if isinstance(approval_result, dict) else bool(approval_result)
    EventService.record_event(
        task_id,
        "APPROVAL_RESOLVED",
        payload={"approval_id": approval_id, "approved": approved, "patch_hash": patch_hash},
    )

    if approved and patch_dict:
        if not ApprovalManager.verify_request(
            approval_id, task_id, "multi-agent-coding", "patch.apply", "apply", appr_req.arguments_summary
        ):
            return {"status": "FAILED", "error": "Approval does not match the proposed patch"}
        patch_obj = Patch(**patch_dict)
        supervisor = SupervisorAgent()
        apply_outcome = supervisor.coding_agent.apply_patch(patch_obj, expected_patch_hash=patch_hash)
        EventService.record_event(
            task_id,
            "PATCH_APPLIED",
            payload={"applied": apply_outcome.get("applied"), "files": apply_outcome.get("modified_files")},
        )
        if not apply_outcome.get("applied"):
            return {"status": "FAILED", "error": apply_outcome.get("error") or str(apply_outcome.get("errors") or "Patch application failed")}
    elif approved:
        return {"status": "FAILED", "error": "No validated patch available to apply"}

    return {
        "approval_resolved": True,
        "approved": approved,
        "approval_status": "APPROVED" if approved else "REJECTED",
        "status": "EXECUTING" if approved else "CANCELLED",
        "pending_coding_id": None,
        "applied_coding_ids": [*state.get("applied_coding_ids", []), state.get("pending_coding_id")],
    }


def security_review_node(state: MultiAgentState) -> Dict[str, Any]:
    """Execute advisory security audit."""
    task_id = state.get("task_id", "task-1")
    supervisor = SupervisorAgent()
    sec_subtask = SubTask(
        task_id=task_id,
        subtask_id=f"sec-review-{task_id[:6]}",
        description="Verify security policies and inspect sensitive access",
        assigned_agent=AgentType.SECURITY,
    )
    sec_res = supervisor.execute_subtask(sec_subtask)
    EventService.record_event(task_id, "SUBTASK_COMPLETED" if sec_res.status == AgentStatus.COMPLETED else "SUBTASK_FAILED", payload=sec_res.model_dump())
    return {"security_passed": sec_res.status == AgentStatus.COMPLETED}


def merge_results_node(state: MultiAgentState) -> Dict[str, Any]:
    """Aggregate execution outcomes and build summary."""
    task_id = state.get("task_id", "task-1")
    instruction = state.get("user_instruction", "")
    subtask_results = state.get("subtask_results", {})

    replacements = state.get("recovery_replacements", {})
    # Failed attempts remain persisted in events/artifacts/state. Only a chain
    # ending in a successful retest supersedes them for the final verdict.
    def recovered(subtask_id):
        visited = set()
        while subtask_id in replacements and subtask_id not in visited:
            visited.add(subtask_id)
            subtask_id = replacements[subtask_id]
        return bool(visited) and subtask_results.get(subtask_id, {}).get("status") == AgentStatus.COMPLETED.value
    agent_results = [AgentResult(**res_dict) for s_id, res_dict in subtask_results.items() if not recovered(s_id)]
    supervisor = SupervisorAgent()
    aggregated = supervisor.aggregator.aggregate(agent_results)
    if state.get("security_passed") is False:
        aggregated["all_succeeded"] = False
    final_text = supervisor.synthesize_response(instruction, aggregated, task_id=task_id)

    EventService.record_event(
        task_id,
        "TASK_COMPLETED" if aggregated.get("all_succeeded") else "TASK_FAILED",
        payload={"aggregated": aggregated, "summary": final_text},
    )

    return {
        "aggregated_results": aggregated,
        "final_response": final_text,
        "status": "COMPLETED" if aggregated.get("all_succeeded") else "FAILED",
    }


def final_response_node(state: MultiAgentState) -> Dict[str, Any]:
    """Terminal node."""
    return {
        "status": state.get("status", "COMPLETED"),
        "final_response": state.get("final_response", ""),
    }
