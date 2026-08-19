"""
AgentOS Phase 7 — Adaptive Workflow State Definition.

TypedDict state for LangGraph adaptive intelligence graph.
Stores bounded metadata and references — never full repository contents.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, TypedDict


class AdaptiveState(TypedDict, total=False):
    task_id: str
    user_instruction: str
    thread_id: str
    status: str
    task_category: str
    complexity: str
    risk_level: str
    strategy: str
    model_routing: Dict[str, Any]
    retrieved_experiences: List[Dict[str, Any]]
    experience_summary: Dict[str, Any]
    learning_analysis: Dict[str, Any]
    learning_recommendations: List[Dict[str, Any]]
    subtasks: List[Dict[str, Any]]
    routing_decisions: List[Dict[str, Any]]
    plan_score: Dict[str, Any]
    budget: Dict[str, Any]
    completed_subtask_ids: List[str]
    subtask_results: Dict[str, Any]
    aggregated_results: Dict[str, Any]
    evaluation: Dict[str, Any]
    approval_required: bool
    approval_id: Optional[str]
    approval_status: Optional[str]
    execution_blocked: bool
    final_response: str
    recorded_experience_id: Optional[str]
    error: Optional[str]
    iteration: int
    retry_count: int
    replan_count: int
