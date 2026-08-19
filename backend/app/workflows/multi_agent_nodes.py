"""
AgentOS Phase 5 — Multi-Agent LangGraph Nodes.

Implements sequential and parallel workflow nodes:
- supervisor_plan
- decompose_task
- parallel_execution
- security_review
- human_approval
- merge_results
- final_response
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from langgraph.types import interrupt

from backend.app.agents.supervisor import SupervisorAgent
from backend.app.config.settings import settings
from backend.app.models.approval import ApprovalRequest, ApprovalStatus
from backend.app.models.multi_agent import AgentResult, AgentStatus, AgentType, SubTask
from backend.app.models.tool import RiskLevel
from backend.app.security.approval import ApprovalManager
from backend.app.services.agent_budget import AgentBudgetTracker
from backend.app.services.event_service import EventService
from backend.app.workflows.multi_agent_state import MultiAgentState

logger = logging.getLogger("agentos.multi_agent_nodes")


def supervisor_plan_node(state: MultiAgentState) -> Dict[str, Any]:
    """Initialize multi-agent coordination task and budget."""
    task_id = state.get("task_id", "task-1")
    instruction = state.get("user_instruction", "")

    EventService.record_event(task_id, "MULTI_AGENT_TASK_STARTED", payload={"instruction": instruction})
    AgentBudgetTracker.initialize_task(task_id)

    return {
        "status": "PLANNING",
        "iteration": 0,
        "completed_subtask_ids": [],
        "subtask_results": {},
    }


def decompose_task_node(state: MultiAgentState) -> Dict[str, Any]:
    """Decompose user request into structured SubTask DAG."""
    task_id = state.get("task_id", "task-1")
    instruction = state.get("user_instruction", "")

    supervisor = SupervisorAgent()
    subtasks = supervisor.plan_and_decompose(instruction, task_id=task_id)

    for st in subtasks:
        EventService.record_event(task_id, "SUBTASK_CREATED", payload=st.model_dump())

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
    """Execute ready subtasks using Supervisor and ParallelExecutor."""
    task_id = state.get("task_id", "task-1")
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

    return {
        "completed_subtask_ids": list(completed_ids),
        "subtask_results": subtask_results,
    }


def human_approval_node(state: MultiAgentState) -> Dict[str, Any]:
    """Human-in-the-loop gate for any code modifications."""
    task_id = state.get("task_id", "task-1")
    approval_id = state.get("approval_id") or f"appr-{task_id[:8]}"

    existing_status = state.get("approval_status")
    if existing_status == "APPROVED":
        return {"status": "EXECUTING"}

    # Register approval request
    req = ApprovalRequest(
        approval_id=approval_id,
        task_id=task_id,
        step_id="multi_agent_patch",
        tool_name="patch",
        operation="apply",
        arguments_hash="multi-agent-patch-hash",
        arguments_summary={"task_id": task_id, "type": "multi_agent_patch"},
        risk_level=RiskLevel.HIGH,
        reason=f"Authorize multi-agent code modification for task {task_id}",
    )
    ApprovalManager.request_approval(req)

    human_res = interrupt({
        "approval_id": approval_id,
        "task_id": task_id,
        "description": "Multi-agent code modification approval",
    })

    approved = human_res.get("approved", True) if isinstance(human_res, dict) else bool(human_res)
    if not approved:
        return {
            "approval_status": "REJECTED",
            "status": "FAILED",
            "error": "Human rejected multi-agent modification.",
        }

    return {
        "approval_status": "APPROVED",
        "status": "EXECUTING",
    }


def security_review_node(state: MultiAgentState) -> Dict[str, Any]:
    """Advisory security scan across all execution artifacts."""
    task_id = state.get("task_id", "task-1")
    EventService.record_event(task_id, "SECURITY_REVIEW_STARTED")

    supervisor = SupervisorAgent()
    sec_st = SubTask(
        task_id=task_id,
        subtask_id="sec_review",
        description="Comprehensive security policy review",
        assigned_agent=AgentType.SECURITY,
        target_files=["calculator.py"],
    )
    sec_res = supervisor.security_agent.execute(sec_st)
    EventService.record_event(task_id, "SECURITY_REVIEW_COMPLETED", payload=sec_res.model_dump())

    return {"status": "EXECUTING"}


def merge_results_node(state: MultiAgentState) -> Dict[str, Any]:
    """Merge and synthesize findings from all completed subtasks."""
    task_id = state.get("task_id", "task-1")
    instruction = state.get("user_instruction", "")
    results_raw = state.get("subtask_results", {})

    agent_results = [AgentResult(**r) for r in results_raw.values()]
    supervisor = SupervisorAgent()
    aggregated = supervisor.aggregator.aggregate(agent_results)

    final_resp = supervisor.synthesize_response(instruction, aggregated, task_id)
    EventService.record_event(task_id, "MULTI_AGENT_TASK_COMPLETED", payload=aggregated)

    return {
        "aggregated_results": aggregated,
        "final_response": final_resp,
        "status": "COMPLETED",
    }


def final_response_node(state: MultiAgentState) -> Dict[str, Any]:
    """Final output terminal node."""
    return {
        "status": state.get("status", "COMPLETED"),
        "final_response": state.get("final_response", ""),
    }
