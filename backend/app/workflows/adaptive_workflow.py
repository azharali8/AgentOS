"""
AgentOS Phase 7 — Adaptive Intelligence LangGraph Workflow.

Full adaptive multi-agent pipeline with SqliteSaver checkpointing.
"""

from __future__ import annotations

import logging
import os
import sqlite3
from typing import Any, Optional

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph

from backend.app.config.settings import settings
from backend.app.workflows.adaptive_nodes import (
    aggregate_node,
    allocate_budget_node,
    classify_node,
    complexity_analysis_node,
    decompose_node,
    evaluate_node,
    execute_node,
    final_response_node,
    historical_analysis_node,
    record_experience_node,
    retrieve_experience_node,
    learn_node,
    route_model_node,
    route_agents_node,
    score_plan_node,
    strategy_selection_node,
)
from backend.app.workflows.adaptive_state import AdaptiveState

logger = logging.getLogger("agentos.adaptive_workflow")

_adaptive_compiled_graph: Optional[Any] = None
_adaptive_sqlite_conn: Optional[sqlite3.Connection] = None
_adaptive_checkpointer: Optional[Any] = None


def _route_after_execute(state: AdaptiveState) -> str:
    subtasks = state.get("subtasks", [])
    completed = set(state.get("completed_subtask_ids", []))
    if state.get("execution_blocked"):
        return "aggregate"
    if state.get("iteration", 0) >= settings.MAX_REPLANS:
        return "aggregate"
    if len(completed) < len(subtasks):
        return "execute"
    return "aggregate"


def build_adaptive_graph() -> StateGraph:
    workflow = StateGraph(AdaptiveState)

    workflow.add_node("classify", classify_node)
    workflow.add_node("complexity_analysis", complexity_analysis_node)
    workflow.add_node("retrieve_experience", retrieve_experience_node)
    workflow.add_node("historical_analysis", historical_analysis_node)
    workflow.add_node("strategy_selection", strategy_selection_node)
    workflow.add_node("route_model", route_model_node)
    workflow.add_node("decompose", decompose_node)
    workflow.add_node("score_plan", score_plan_node)
    workflow.add_node("route_agents", route_agents_node)
    workflow.add_node("allocate_budget", allocate_budget_node)
    workflow.add_node("execute", execute_node)
    workflow.add_node("aggregate", aggregate_node)
    workflow.add_node("evaluate", evaluate_node)
    workflow.add_node("learn", learn_node)
    workflow.add_node("record_experience", record_experience_node)
    workflow.add_node("final_response", final_response_node)

    workflow.add_edge(START, "classify")
    workflow.add_edge("classify", "complexity_analysis")
    workflow.add_edge("complexity_analysis", "retrieve_experience")
    workflow.add_edge("retrieve_experience", "historical_analysis")
    workflow.add_edge("historical_analysis", "strategy_selection")
    workflow.add_edge("strategy_selection", "route_model")
    workflow.add_edge("route_model", "decompose")
    workflow.add_edge("decompose", "score_plan")
    workflow.add_edge("score_plan", "route_agents")
    workflow.add_edge("route_agents", "allocate_budget")
    workflow.add_edge("allocate_budget", "execute")

    workflow.add_conditional_edges(
        "execute",
        _route_after_execute,
        {"execute": "execute", "aggregate": "aggregate"},
    )

    workflow.add_edge("aggregate", "evaluate")
    workflow.add_edge("evaluate", "learn")
    workflow.add_edge("learn", "record_experience")
    workflow.add_edge("record_experience", "final_response")
    workflow.add_edge("final_response", END)

    return workflow


def get_adaptive_graph(checkpointer: Optional[Any] = None) -> Any:
    global _adaptive_compiled_graph, _adaptive_sqlite_conn, _adaptive_checkpointer

    if _adaptive_compiled_graph is not None and checkpointer is None:
        return _adaptive_compiled_graph

    if checkpointer is not None:
        return build_adaptive_graph().compile(checkpointer=checkpointer)

    db_path = settings.DATABASE_URL.replace("sqlite:///", "")
    os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
    _adaptive_sqlite_conn = sqlite3.connect(db_path, check_same_thread=False)
    _adaptive_checkpointer = SqliteSaver(_adaptive_sqlite_conn)
    _adaptive_compiled_graph = build_adaptive_graph().compile(checkpointer=_adaptive_checkpointer)

    return _adaptive_compiled_graph
