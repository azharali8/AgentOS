"""
AgentOS Phase 5 — Multi-Agent State Definition.

TypedDict state for LangGraph multi-agent coordination graph.
Stores bounded metadata, subtasks, DAG progress, and aggregated summaries.
Never dumps complete repository source trees into graph state.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, TypedDict


class MultiAgentState(TypedDict, total=False):
    task_id: str
    user_instruction: str
    thread_id: str
    status: str  # PLANNING | EXECUTING | WAITING_APPROVAL | COMPLETED | FAILED
    iteration: int
    subtasks: List[Dict[str, Any]]
    completed_subtask_ids: List[str]
    subtask_results: Dict[str, Any]
    aggregated_results: Dict[str, Any]
    approval_required: bool
    approval_id: Optional[str]
    approval_status: Optional[str]
    patch_hash: Optional[str]
    final_response: str
    error: Optional[str]
