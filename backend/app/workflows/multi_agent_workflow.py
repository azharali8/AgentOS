"""
AgentOS Phase 5 — Compiled Multi-Agent StateGraph.

Coordinates the end-to-end multi-agent execution pipeline with SqliteSaver checkpointing.
"""

from __future__ import annotations

import logging
import os
import sqlite3
from typing import Any, Optional

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph

from backend.app.config.settings import settings
from backend.app.workflows.multi_agent_nodes import (
    decompose_task_node,
    final_response_node,
    human_approval_node,
    merge_results_node,
    parallel_execution_node,
    security_review_node,
    supervisor_plan_node,
)
from backend.app.workflows.multi_agent_state import MultiAgentState

logger = logging.getLogger("agentos.multi_agent_workflow")

_multi_agent_compiled_graph: Optional[Any] = None
_multi_agent_sqlite_conn: Optional[sqlite3.Connection] = None
_multi_agent_checkpointer: Optional[Any] = None


def _route_after_execution(state: MultiAgentState) -> str:
    """Check if all subtasks are finished or if further DAG iterations needed."""
    subtasks = state.get("subtasks", [])
    completed_ids = set(state.get("completed_subtask_ids", []))

    if state.get("status") in ("FAILED", "CANCELLED", "PAUSED"):
        return "final_response"
    if state.get("pending_coding_id"):
        return "human_approval"

    if len(completed_ids) < len(subtasks):
        return "parallel_execution"

    return "security_review"


def _route_after_approval(state: MultiAgentState) -> str:
    if state.get("status") in ("FAILED", "CANCELLED") or state.get("approval_status") == "REJECTED":
        return "final_response"
    return "parallel_execution"


def build_multi_agent_graph() -> StateGraph:
    """Construct the StateGraph for multi-agent collaboration."""
    workflow = StateGraph(MultiAgentState)

    workflow.add_node("supervisor_plan", supervisor_plan_node)
    workflow.add_node("decompose_task", decompose_task_node)
    workflow.add_node("parallel_execution", parallel_execution_node)
    workflow.add_node("human_approval", human_approval_node)
    workflow.add_node("security_review", security_review_node)
    workflow.add_node("merge_results", merge_results_node)
    workflow.add_node("final_response", final_response_node)

    workflow.add_edge(START, "supervisor_plan")
    workflow.add_edge("supervisor_plan", "decompose_task")
    workflow.add_edge("decompose_task", "parallel_execution")

    workflow.add_conditional_edges(
        "parallel_execution",
        _route_after_execution,
        {
            "parallel_execution": "parallel_execution",
            "human_approval": "human_approval",
            "security_review": "security_review",
            "final_response": "final_response",
        },
    )

    workflow.add_conditional_edges(
        "human_approval",
        _route_after_approval,
        {
            "parallel_execution": "parallel_execution",
            "final_response": "final_response",
        },
    )

    workflow.add_edge("security_review", "merge_results")
    workflow.add_edge("merge_results", "final_response")
    workflow.add_edge("final_response", END)

    return workflow


def get_multi_agent_graph(checkpointer: Optional[Any] = None) -> Any:
    """Compile and return the multi-agent StateGraph."""
    global _multi_agent_compiled_graph, _multi_agent_sqlite_conn, _multi_agent_checkpointer

    if _multi_agent_compiled_graph is not None and checkpointer is None:
        return _multi_agent_compiled_graph

    if checkpointer is not None:
        return build_multi_agent_graph().compile(checkpointer=checkpointer)

    db_path = settings.DATABASE_URL.replace("sqlite:///", "")
    os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
    _multi_agent_sqlite_conn = sqlite3.connect(db_path, check_same_thread=False)
    _multi_agent_checkpointer = SqliteSaver(_multi_agent_sqlite_conn)
    _multi_agent_compiled_graph = build_multi_agent_graph().compile(checkpointer=_multi_agent_checkpointer)

    return _multi_agent_compiled_graph
