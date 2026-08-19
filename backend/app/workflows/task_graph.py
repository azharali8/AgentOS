"""
AgentOS Phase 2 — LangGraph Execution Graph with Persistent SQLite Checkpointing

Full 8-node StateGraph implementing the agentic execution pipeline:

    START
    → plan_node          (LLM → structured plan)
    → select_tool_node   (pick next step, enforce limits)
    → security_node      (policy check → DENY / NEEDS_APPROVAL / PASS)
    → approval_node      (interrupt() → wait for human → verify → re-validate security)
    → execute_node       (ExecutionManager.execute_tool)
    → observe_node       (wrap result in Observation)
    → review_node        (LLM → SUCCESS / RETRYABLE / FATAL)
    → replan_node        (LLM → revised plan)
    → END

Phase 2 additions:
  - Persistent SQLite checkpointing via SqliteSaver
  - Domain events emitted to EventService at each state transition
  - Execution lifecycle and cancellation managed by ExecutionManager
  - Cryptographic argument hash validation on approval resolution
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

from backend.app.agents.planner import Planner, PlannerError
from backend.app.agents.reviewer import ReviewerAgent
from backend.app.config.settings import settings
from backend.app.models.agent import AgentState, Observation, PlanStep
from backend.app.models.approval import ApprovalRequest, ApprovalStatus
from backend.app.models.tool import RiskLevel, ToolRequest, ToolResult
from backend.app.security.approval import ApprovalManager
from backend.app.security.permissions import SecurityManager
from backend.app.security.policies import get_policy
from backend.app.services.event_service import EventService
from backend.app.services.execution_manager import ExecutionManager
from backend.app.services.task_service import TaskService
from backend.app.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)

_checkpointer: Optional[Any] = None
_compiled_graph: Optional[Any] = None
_sqlite_conn: Optional[sqlite3.Connection] = None


def _get_checkpointer() -> Any:
    global _checkpointer, _sqlite_conn
    if _checkpointer is None:
        db_url = settings.DATABASE_URL
        if db_url.startswith("sqlite"):
            # Extract relative or absolute sqlite filepath
            db_path = db_url.replace("sqlite:///", "").replace("sqlite://", "")
            os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
            _sqlite_conn = sqlite3.connect(db_path, check_same_thread=False)
            _checkpointer = SqliteSaver(_sqlite_conn)
            # Setup tables for sqlite checkpointer if needed
            _checkpointer.setup()
        else:
            _checkpointer = MemorySaver()
    return _checkpointer


# ---------------------------------------------------------------------------
# Node functions
# ---------------------------------------------------------------------------

def plan_node(state: AgentState, config: RunnableConfig) -> Dict:
    """Call Planner → produce structured plan. Enforce MAX_PLAN_STEPS."""
    task_id = state["task_id"]

    if ExecutionManager.is_cancelled(task_id):
        TaskService.update_task_status(task_id, _status("CANCELLED"))
        return {"task_status": "CANCELLED", "next_node": "end"}

    EventService.record_event(
        task_id=task_id,
        event_type="TASK_STARTED",
        payload={"user_request": state.get("user_request")},
    )

    llm = _get_llm(config)
    planner = Planner(llm)

    try:
        steps = planner.plan(state)
    except PlannerError as exc:
        msg = f"Planning failed: {exc}"
        TaskService.set_error(task_id, msg)
        EventService.record_event(
            task_id=task_id,
            event_type="TASK_FAILED",
            payload={"error": msg},
        )
        return {
            "task_status": "FAILED",
            "error": msg,
            "next_node": "end",
        }

    if not steps:
        msg = "No actions required to complete the task."
        TaskService.set_final_response(task_id, msg)
        TaskService.update_task_status(task_id, _status("COMPLETED"))
        EventService.record_event(
            task_id=task_id,
            event_type="TASK_COMPLETED",
            payload={"final_response": msg},
        )
        return {
            "task_status": "COMPLETED",
            "final_response": msg,
            "plan": [],
            "current_step_index": 0,
            "next_node": "end",
        }

    plan_dicts = [s.model_dump() for s in steps]
    TaskService.update_task_status(task_id, _status("PLANNING"))

    EventService.record_event(
        task_id=task_id,
        event_type="PLAN_CREATED",
        payload={"total_steps": len(steps), "steps": [s.step_id for s in steps]},
    )

    return {
        "plan": plan_dicts,
        "current_step_index": 0,
        "retry_count": 0,
        "replan_count": 0,
        "tool_call_count": 0,
        "next_node": "select",
    }


def select_tool_node(state: AgentState) -> Dict:
    """Pick the current step from the plan. Enforce MAX_TOOL_CALLS."""
    task_id = state["task_id"]
    idx = state["current_step_index"]
    plan = state["plan"]

    if ExecutionManager.is_cancelled(task_id):
        TaskService.update_task_status(task_id, _status("CANCELLED"))
        return {"task_status": "CANCELLED", "next_node": "end"}

    # Hard limits enforced server-side — LLM cannot override
    if state["tool_call_count"] >= settings.MAX_TOOL_CALLS:
        msg = f"MAX_TOOL_CALLS ({settings.MAX_TOOL_CALLS}) reached."
        TaskService.set_error(task_id, msg)
        EventService.record_event(
            task_id=task_id,
            event_type="TASK_FAILED",
            payload={"error": msg},
        )
        return {
            "task_status": "FAILED",
            "error": msg,
            "next_node": "end",
        }

    if idx >= len(plan):
        # Plan exhausted — all steps done
        response = _build_final_response(state)
        TaskService.set_final_response(task_id, response)
        TaskService.update_task_status(task_id, _status("COMPLETED"))
        EventService.record_event(
            task_id=task_id,
            event_type="TASK_COMPLETED",
            payload={"final_response": response},
        )
        return {
            "task_status": "COMPLETED",
            "final_response": response,
            "next_node": "end",
        }

    step_dict = plan[idx]
    step = PlanStep.model_validate(step_dict)
    tool_request = {
        "tool_name": step.tool_name,
        "arguments": {"operation": step.operation, **step.arguments},
    }

    TaskService.update_task_status(task_id, _status("EXECUTING"))
    EventService.record_event(
        task_id=task_id,
        event_type="STEP_SELECTED",
        step_id=step.step_id,
        payload={"tool_name": step.tool_name, "operation": step.operation, "step_index": idx},
    )

    return {
        "current_tool_request": tool_request,
        "tool_call_count": state["tool_call_count"] + 1,
        "next_node": "security",
    }


def security_node(state: AgentState) -> Dict:
    """Policy check. Routes to: deny | approval | execute."""
    task_id = state["task_id"]
    req_dict = state["current_tool_request"]
    if not req_dict:
        TaskService.set_error(task_id, "No tool request set.")
        return {"task_status": "FAILED", "error": "No tool request set.", "next_node": "end"}

    tool_name = req_dict["tool_name"]
    operation = req_dict["arguments"].get("operation", "default")
    idx = state["current_step_index"]
    plan = state["plan"]
    step_id = plan[idx].get("step_id", f"step-{idx}") if idx < len(plan) else f"step-{idx}"

    is_allowed = SecurityManager.is_allowed(tool_name, operation)
    requires_approval = SecurityManager.requires_approval(tool_name, operation)

    EventService.record_event(
        task_id=task_id,
        event_type="SECURITY_CHECKED",
        step_id=step_id,
        payload={
            "tool_name": tool_name,
            "operation": operation,
            "is_allowed": is_allowed,
            "requires_approval": requires_approval,
        },
    )

    if not is_allowed:
        msg = f"Security: Operation DENIED — {tool_name}.{operation}"
        TaskService.set_error(task_id, msg)
        EventService.record_event(
            task_id=task_id,
            event_type="TASK_FAILED",
            step_id=step_id,
            payload={"error": msg},
        )
        return {
            "task_status": "FAILED",
            "error": msg,
            "next_node": "end",
        }

    if requires_approval:
        approval_id = str(uuid.uuid4())
        app_req = ApprovalRequest(
            approval_id=approval_id,
            task_id=task_id,
            step_id=step_id,
            tool_name=tool_name,
            operation=operation,
            arguments_hash="",  # Computed inside ApprovalManager
            arguments_summary=req_dict["arguments"],
            risk_level=get_policy(tool_name, operation),
            reason="Requires human approval per security policy",
        )
        ApprovalManager.request_approval(app_req)
        TaskService.set_pending_approval(task_id, approval_id)

        EventService.record_event(
            task_id=task_id,
            event_type="APPROVAL_REQUIRED",
            step_id=step_id,
            payload={"approval_id": approval_id, "tool_name": tool_name, "operation": operation},
        )

        return {
            "pending_approval_id": approval_id,
            "next_node": "approval",
        }

    return {"next_node": "execute"}


def approval_node(state: AgentState) -> Dict:
    """
    LangGraph interrupt point for human-in-the-loop approval.
    """
    task_id = state["task_id"]
    approval_id = state["pending_approval_id"]
    req_dict = state["current_tool_request"]
    idx = state["current_step_index"]
    plan = state["plan"]
    step_id = plan[idx].get("step_id", f"step-{idx}") if idx < len(plan) else f"step-{idx}"
    operation = req_dict["arguments"].get("operation", "default")
    tool_name = req_dict["tool_name"]

    # Pause execution — wait for human resolution via API
    resume_value: Dict = interrupt({
        "approval_id": approval_id,
        "tool_name": tool_name,
        "operation": operation,
        "arguments": req_dict["arguments"],
        "task_id": task_id,
        "step_id": step_id,
    })

    # --- Execution resumes here after Command(resume=...) ---
    approved: bool = resume_value.get("approved", False)
    resumed_approval_id: str = resume_value.get("approval_id", "")

    # 1. Verify approval_id integrity
    if resumed_approval_id != approval_id:
        msg = f"Approval ID mismatch: expected {approval_id}, got {resumed_approval_id}"
        TaskService.set_error(task_id, msg)
        EventService.record_event(
            task_id=task_id,
            event_type="TASK_FAILED",
            step_id=step_id,
            payload={"error": msg},
        )
        return {
            "task_status": "FAILED",
            "error": msg,
            "next_node": "end",
        }

    # 2. Cryptographic hash verification of exact request parameters
    is_valid = ApprovalManager.verify_request(
        approval_id=approval_id,
        task_id=task_id,
        step_id=step_id,
        tool_name=tool_name,
        operation=operation,
        arguments=req_dict["arguments"],
    )
    if not is_valid:
        msg = "Approval verification failed: arguments or step hash mismatch (substitution attack prevented)."
        TaskService.set_error(task_id, msg)
        EventService.record_event(
            task_id=task_id,
            event_type="TASK_FAILED",
            step_id=step_id,
            payload={"error": msg},
        )
        return {
            "task_status": "FAILED",
            "error": msg,
            "next_node": "end",
        }

    # 3. Rejected → FAILED
    if not approved:
        ApprovalManager.resolve_approval(approval_id, ApprovalStatus.REJECTED, "User rejected")
        msg = f"Approval rejected for {tool_name}.{operation}"
        TaskService.set_error(task_id, msg)
        EventService.record_event(
            task_id=task_id,
            event_type="APPROVAL_REJECTED",
            step_id=step_id,
            payload={"approval_id": approval_id},
        )
        return {
            "task_status": "FAILED",
            "error": msg,
            "next_node": "end",
        }

    # 4. Approved
    ApprovalManager.resolve_approval(approval_id, ApprovalStatus.APPROVED, "User approved")
    EventService.record_event(
        task_id=task_id,
        event_type="APPROVAL_APPROVED",
        step_id=step_id,
        payload={"approval_id": approval_id},
    )

    # 5. Security re-validation
    if not SecurityManager.is_allowed(tool_name, operation):
        msg = f"Security re-validation DENIED post-approval: {tool_name}.{operation}"
        TaskService.set_error(task_id, msg)
        EventService.record_event(
            task_id=task_id,
            event_type="TASK_FAILED",
            step_id=step_id,
            payload={"error": msg},
        )
        return {
            "task_status": "FAILED",
            "error": msg,
            "next_node": "end",
        }

    return {
        "pending_approval_id": None,
        "next_node": "execute",
    }


def execute_node(state: AgentState) -> Dict:
    """Execute the current tool request via ExecutionManager."""
    task_id = state["task_id"]
    req_dict = state["current_tool_request"]
    idx = state["current_step_index"]
    plan = state["plan"]
    step_id = plan[idx].get("step_id", f"step-{idx}") if idx < len(plan) else f"step-{idx}"

    request = ToolRequest(
        tool_name=req_dict["tool_name"],
        arguments=req_dict["arguments"],
    )

    result: ToolResult = ExecutionManager.execute_tool(
        task_id=task_id,
        step_id=step_id,
        request=request,
        is_post_approval=True,
        retry_number=state.get("retry_count", 0),
    )

    result_dict = {
        "tool_name": result.tool_name,
        "success": result.success,
        "data": result.data,
        "error": result.error,
    }
    return {
        "tool_results": [*state.get("tool_results", []), result_dict],
        "next_node": "observe",
    }


def observe_node(state: AgentState) -> Dict:
    """Wrap the latest tool result in a typed Observation."""
    task_id = state["task_id"]
    plan = state["plan"]
    idx = state["current_step_index"]
    step = PlanStep.model_validate(plan[idx]) if idx < len(plan) else None

    latest_result = (state.get("tool_results") or [{}])[-1]
    obs = Observation(
        step_id=step.step_id if step else f"step-{idx}",
        tool_name=latest_result.get("tool_name", "unknown"),
        operation=state["current_tool_request"]["arguments"].get("operation", "unknown"),
        success=latest_result.get("success", False),
        data=latest_result.get("data"),
        error=latest_result.get("error"),
    )

    EventService.record_event(
        task_id=task_id,
        event_type="OBSERVATION_CREATED",
        step_id=obs.step_id,
        payload={"success": obs.success, "tool_name": obs.tool_name, "operation": obs.operation},
    )

    return {
        "observations": [*state.get("observations", []), obs.model_dump()],
        "next_node": "review",
    }


def review_node(state: AgentState, config: RunnableConfig) -> Dict:
    """LLM reviews observation. Routes to: next_step | replan | end."""
    task_id = state["task_id"]
    llm = _get_llm(config)
    reviewer = ReviewerAgent(llm)

    plan = state["plan"]
    idx = state["current_step_index"]
    step = PlanStep.model_validate(plan[idx]) if idx < len(plan) else None
    latest_obs_dict = (state.get("observations") or [{}])[-1]
    obs = Observation.model_validate(latest_obs_dict)

    TaskService.update_task_status(task_id, _status("REVIEWING"))
    verdict, reasoning = reviewer.review(step or _dummy_step(idx), obs)

    EventService.record_event(
        task_id=task_id,
        event_type="REVIEW_COMPLETED",
        step_id=step.step_id if step else f"step-{idx}",
        payload={"verdict": verdict, "reasoning": reasoning},
    )

    if verdict == "SUCCESS":
        next_idx = idx + 1
        if next_idx >= len(plan):
            response = _build_final_response(state)
            TaskService.set_final_response(task_id, response)
            EventService.record_event(
                task_id=task_id,
                event_type="TASK_COMPLETED",
                payload={"final_response": response},
            )
            return {
                "review_verdict": verdict,
                "review_reasoning": reasoning,
                "current_step_index": next_idx,
                "retry_count": 0,
                "task_status": "COMPLETED",
                "final_response": response,
                "next_node": "end",
            }
        return {
            "review_verdict": verdict,
            "review_reasoning": reasoning,
            "current_step_index": next_idx,
            "retry_count": 0,
            "next_node": "select",
        }

    elif verdict == "RETRYABLE":
        retry_count = state.get("retry_count", 0) + 1
        replan_count = state.get("replan_count", 0)

        if retry_count > settings.MAX_RETRIES_PER_STEP:
            if replan_count >= settings.MAX_REPLANS:
                TaskService.set_error(task_id, "MAX_REPLANS reached after retries")
                EventService.record_event(
                    task_id=task_id,
                    event_type="TASK_FAILED",
                    payload={"error": "MAX_REPLANS reached after retries"},
                )
                return {
                    "review_verdict": verdict,
                    "task_status": "FAILED",
                    "error": "MAX_REPLANS reached",
                    "next_node": "end",
                }
            return {
                "review_verdict": verdict,
                "review_reasoning": reasoning,
                "retry_count": retry_count,
                "next_node": "replan",
            }
        return {
            "review_verdict": verdict,
            "review_reasoning": reasoning,
            "retry_count": retry_count,
            "next_node": "select",
        }

    else:  # FATAL
        TaskService.set_error(task_id, f"Fatal error: {reasoning}")
        EventService.record_event(
            task_id=task_id,
            event_type="TASK_FAILED",
            payload={"error": f"Fatal error at step {idx}: {reasoning}"},
        )
        return {
            "review_verdict": verdict,
            "review_reasoning": reasoning,
            "task_status": "FAILED",
            "error": f"Fatal error at step {idx}: {reasoning}",
            "next_node": "end",
        }


def replan_node(state: AgentState, config: RunnableConfig) -> Dict:
    """LLM generates a revised plan. Enforce MAX_REPLANS."""
    task_id = state["task_id"]
    replan_count = state.get("replan_count", 0) + 1

    EventService.record_event(
        task_id=task_id,
        event_type="REPLAN_STARTED",
        payload={"replan_count": replan_count},
    )

    if replan_count > settings.MAX_REPLANS:
        msg = f"MAX_REPLANS ({settings.MAX_REPLANS}) exceeded."
        TaskService.set_error(task_id, msg)
        EventService.record_event(
            task_id=task_id,
            event_type="TASK_FAILED",
            payload={"error": msg},
        )
        return {
            "task_status": "FAILED",
            "error": msg,
            "next_node": "end",
        }

    llm = _get_llm(config)
    planner = Planner(llm)
    try:
        new_steps = planner.replan(state)
    except PlannerError as exc:
        msg = f"Replanning failed: {exc}"
        TaskService.set_error(task_id, msg)
        EventService.record_event(
            task_id=task_id,
            event_type="TASK_FAILED",
            payload={"error": msg},
        )
        return {
            "task_status": "FAILED",
            "error": msg,
            "next_node": "end",
        }

    new_plan = [s.model_dump() for s in new_steps]
    EventService.record_event(
        task_id=task_id,
        event_type="REPLAN_COMPLETED",
        payload={"replan_count": replan_count, "new_total_steps": len(new_steps)},
    )

    return {
        "plan": new_plan,
        "current_step_index": 0,
        "replan_count": replan_count,
        "retry_count": 0,
        "next_node": "select",
    }


# ---------------------------------------------------------------------------
# Routing functions (conditional edges)
# ---------------------------------------------------------------------------

def _route(state: AgentState) -> str:
    return state.get("next_node", "end")


def _route_security(state: AgentState) -> str:
    nxt = state.get("next_node", "end")
    if nxt == "end":
        return END
    if nxt == "approval":
        return "approval_node"
    return "execute_node"


def _route_review(state: AgentState) -> str:
    nxt = state.get("next_node", "end")
    if nxt == "select":
        return "select_tool_node"
    if nxt == "replan":
        return "replan_node"
    return END


def _route_after_plan(state: AgentState) -> str:
    nxt = state.get("next_node", "end")
    if nxt == "select":
        return "select_tool_node"
    return END


def _route_after_select(state: AgentState) -> str:
    nxt = state.get("next_node", "end")
    if nxt == "security":
        return "security_node"
    return END


def _route_after_approval(state: AgentState) -> str:
    nxt = state.get("next_node", "end")
    if nxt == "execute":
        return "execute_node"
    return END


def _route_after_replan(state: AgentState) -> str:
    nxt = state.get("next_node", "end")
    if nxt == "select":
        return "select_tool_node"
    return END


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_llm(config: RunnableConfig):
    llm = (config or {}).get("configurable", {}).get("llm")
    if llm is not None:
        return llm
    from backend.app.llm.factory import get_llm_provider
    return get_llm_provider()


def _status(name: str):
    from backend.app.models.task import TaskStatus
    return TaskStatus(name)


def _dummy_step(idx: int) -> PlanStep:
    return PlanStep(
        step_id=f"step-{idx}",
        tool_name="unknown",
        operation="unknown",
        arguments={},
        description="Unknown step",
    )


def _build_final_response(state: AgentState) -> str:
    obs = state.get("observations", [])
    if not obs:
        return "Task completed with no observations."
    last = obs[-1]
    data = last.get("data")
    return str(data) if data is not None else "Task completed successfully."


# ---------------------------------------------------------------------------
# Graph construction
# ---------------------------------------------------------------------------

def build_graph(checkpointer: Optional[Any] = None) -> Any:
    """Build and compile the LangGraph StateGraph."""
    g = StateGraph(AgentState)

    g.add_node("plan_node", plan_node)
    g.add_node("select_tool_node", select_tool_node)
    g.add_node("security_node", security_node)
    g.add_node("approval_node", approval_node)
    g.add_node("execute_node", execute_node)
    g.add_node("observe_node", observe_node)
    g.add_node("review_node", review_node)
    g.add_node("replan_node", replan_node)

    g.add_edge(START, "plan_node")
    g.add_conditional_edges("plan_node", _route_after_plan,
                            {"select_tool_node": "select_tool_node", END: END})
    g.add_conditional_edges("select_tool_node", _route_after_select,
                            {"security_node": "security_node", END: END})
    g.add_conditional_edges("security_node", _route_security,
                            {"approval_node": "approval_node",
                             "execute_node": "execute_node",
                             END: END})
    g.add_conditional_edges("approval_node", _route_after_approval,
                            {"execute_node": "execute_node", END: END})
    g.add_edge("execute_node", "observe_node")
    g.add_edge("observe_node", "review_node")
    g.add_conditional_edges("review_node", _route_review,
                            {"select_tool_node": "select_tool_node",
                             "replan_node": "replan_node",
                             END: END})
    g.add_conditional_edges("replan_node", _route_after_replan,
                            {"select_tool_node": "select_tool_node", END: END})

    cp = checkpointer if checkpointer is not None else _get_checkpointer()
    return g.compile(checkpointer=cp)


def get_compiled_graph() -> Any:
    """Return the singleton compiled graph (lazy init)."""
    global _compiled_graph
    if _compiled_graph is None:
        _compiled_graph = build_graph()
    return _compiled_graph


def reset_graph(memory_only: bool = False) -> None:
    """Reset the singleton — used in tests to get a clean graph."""
    global _compiled_graph, _checkpointer, _sqlite_conn
    _compiled_graph = None
    if _sqlite_conn:
        try:
            _sqlite_conn.close()
        except Exception:
            pass
        _sqlite_conn = None
    if memory_only:
        _checkpointer = MemorySaver()
    else:
        _checkpointer = None
