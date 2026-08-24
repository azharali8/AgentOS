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
            runnable.append(st)

    if not runnable:
        return {"status": "EXECUTING"}

    # Execute runnable batch
    batch_results = supervisor.executor.execute_batch(
        subtasks=runnable,
        runner_fn=supervisor.execute_subtask,
        task_id=task_id,
    )

    for s_id, res in batch_results.items():
        completed_ids.add(s_id)
        subtask_results[s_id] = res.model_dump()
        EventService.record_event(task_id, "SUBTASK_COMPLETED", payload=res.model_dump())

        if res.agent_type == AgentType.CODING and res.evidence.get("patch"):
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

    return {
        "completed_subtask_ids": list(completed_ids),
        "subtask_results": subtask_results,
        "status": "EXECUTING",
    }


def human_approval_node(state: MultiAgentState) -> Dict[str, Any]:
    """Human-in-the-loop gate binding SHA-256 patch hash."""
    task_id = state.get("task_id", "task-1")
    subtask_results = state.get("subtask_results", {})

    coding_res_dict = next(
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
        patch_obj = Patch(**patch_dict)
        supervisor = SupervisorAgent()
        apply_outcome = supervisor.coding_agent.apply_patch(patch_obj, expected_patch_hash=patch_hash)
        EventService.record_event(
            task_id,
            "PATCH_APPLIED",
            payload={"applied": apply_outcome.get("applied"), "files": apply_outcome.get("modified_files")},
        )

    return {
        "approval_resolved": True,
        "approved": approved,
        "status": "EXECUTING" if approved else "CANCELLED",
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
    return {"security_passed": sec_res.status == AgentStatus.COMPLETED}


def merge_results_node(state: MultiAgentState) -> Dict[str, Any]:
    """Aggregate execution outcomes and build summary."""
    task_id = state.get("task_id", "task-1")
    instruction = state.get("user_instruction", "")
    subtask_results = state.get("subtask_results", {})

    agent_results = [AgentResult(**res_dict) for res_dict in subtask_results.values()]
    supervisor = SupervisorAgent()
    aggregated = supervisor.aggregator.aggregate(agent_results)
    final_text = supervisor.synthesize_response(instruction, aggregated, task_id=task_id)

    EventService.record_event(
        task_id,
        "TASK_COMPLETED",
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
