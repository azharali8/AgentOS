"""
AgentOS Phase 4 — LangGraph Compiled Autonomous Coding StateGraph.

Coordinates iterative diagnosis, patch formulation, cryptographic approval,
patch application, post-patch test evaluation, regression rollback, and reporting.
Integrates directly with LangGraph SqliteSaver checkpointer.
"""

from __future__ import annotations

import logging
import os
import sqlite3
from typing import Any, Optional

from langgraph.checkpoint.memory import MemorySaver
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph

from backend.app.config.settings import settings
from backend.app.workflows.coding_nodes import (
    analyze_failures_node,
    analyze_repository_node,
    apply_patch_node,
    approval_node,
    classify_task_node,
    diagnose_node,
    final_response_node,
    generate_patch_node,
    investigate_code_node,
    judge_result_node,
    run_initial_tests_node,
    run_post_patch_tests_node,
)
from backend.app.workflows.coding_state import CodingAgentState

logger = logging.getLogger("agentos.coding_workflow")

_coding_checkpointer: Optional[Any] = None
_coding_compiled_graph: Optional[Any] = None
_coding_sqlite_conn: Optional[sqlite3.Connection] = None


def _route_after_judge(state: CodingAgentState) -> str:
    """Evaluate outcome after post-patch testing."""
    verdict = state.get("judge_verdict", {}).get("verdict", "")
    iteration = state.get("iteration", 0)
    max_iterations = state.get("max_iterations", 5)

    if verdict == "SUCCESS":
        return "final_response"

    if iteration >= max_iterations:
        return "final_response"

    if verdict == "REGRESSION":
        return "final_response"  # In regression, halt safely and produce report

    # STILL_FAILING or NEW_FAILURE: continue investigation loop
    return "investigate_code"


def _route_after_approval(state: CodingAgentState) -> str:
    """Route after approval interrupt resolution."""
    status = state.get("approval_status")
    if status == "REJECTED":
        return "final_response"
    return "apply_patch"


def build_coding_graph() -> StateGraph:
    """Construct the StateGraph for the autonomous coding workflow."""
    workflow = StateGraph(CodingAgentState)

    # 1. Add all nodes
    workflow.add_node("classify_task", classify_task_node)
    workflow.add_node("analyze_repository", analyze_repository_node)
    workflow.add_node("run_initial_tests", run_initial_tests_node)
    workflow.add_node("analyze_failures", analyze_failures_node)
    workflow.add_node("investigate_code", investigate_code_node)
    workflow.add_node("diagnose", diagnose_node)
    workflow.add_node("generate_patch", generate_patch_node)
    workflow.add_node("approval", approval_node)
    workflow.add_node("apply_patch", apply_patch_node)
    workflow.add_node("run_post_patch_tests", run_post_patch_tests_node)
    workflow.add_node("judge_result", judge_result_node)
    workflow.add_node("final_response", final_response_node)

    # 2. Add sequential and conditional edges
    workflow.add_edge(START, "classify_task")
    workflow.add_edge("classify_task", "analyze_repository")
    workflow.add_edge("analyze_repository", "run_initial_tests")
    workflow.add_edge("run_initial_tests", "analyze_failures")
    workflow.add_edge("analyze_failures", "investigate_code")
    workflow.add_edge("investigate_code", "diagnose")
    workflow.add_edge("diagnose", "generate_patch")
    workflow.add_edge("generate_patch", "approval")

    workflow.add_conditional_edges(
        "approval",
        _route_after_approval,
        {
            "apply_patch": "apply_patch",
            "final_response": "final_response",
        }
    )

    workflow.add_edge("apply_patch", "run_post_patch_tests")
    workflow.add_edge("run_post_patch_tests", "judge_result")

    workflow.add_conditional_edges(
        "judge_result",
        _route_after_judge,
        {
            "final_response": "final_response",
            "investigate_code": "investigate_code",
        }
    )

    workflow.add_edge("final_response", END)
    return workflow


def get_coding_graph(checkpointer: Optional[Any] = None) -> Any:
    """Compile and return the autonomous coding StateGraph with checkpointer."""
    global _coding_checkpointer, _coding_compiled_graph, _coding_sqlite_conn

    if _coding_compiled_graph is not None and checkpointer is None:
        return _coding_compiled_graph

    if checkpointer is not None:
        return build_coding_graph().compile(checkpointer=checkpointer)

    # Use SQLite checkpointer connected to DATABASE_URL
    db_path = settings.DATABASE_URL.replace("sqlite:///", "")
    os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
    _coding_sqlite_conn = sqlite3.connect(db_path, check_same_thread=False)
    _coding_checkpointer = SqliteSaver(_coding_sqlite_conn)
    _coding_compiled_graph = build_coding_graph().compile(checkpointer=_coding_checkpointer)

    return _coding_compiled_graph
