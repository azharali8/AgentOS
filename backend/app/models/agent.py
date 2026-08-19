"""
AgentOS Phase 1 — Agent state and structured data models.

AgentState is a TypedDict for LangGraph StateGraph compatibility.
PlanStep, Observation, PlannerOutput, ReviewerOutput are Pydantic models
used at validation boundaries.

NOTE: Task/approval state is held in-process (MemorySaver + TaskService).
      State is lost on process restart. Persistent storage is Phase 2+.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, TypedDict

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Pydantic boundary models (validated at parse time)
# ---------------------------------------------------------------------------

class PlanStep(BaseModel):
    """A single validated step produced by the Planner."""
    step_id: str
    tool_name: str
    operation: str
    arguments: Dict[str, Any] = Field(default_factory=dict)
    description: str

    def to_tool_request_dict(self) -> Dict[str, Any]:
        return {
            "tool_name": self.tool_name,
            "arguments": {"operation": self.operation, **self.arguments},
        }


class Observation(BaseModel):
    """Result of executing a single PlanStep."""
    step_id: str
    tool_name: str
    operation: str
    success: bool
    data: Any = None
    error: Optional[str] = None
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class PlannerOutput(BaseModel):
    """Pydantic model for LLM planner response validation."""
    steps: List[PlanStep]


class ReviewerOutput(BaseModel):
    """Pydantic model for LLM reviewer response validation."""
    verdict: str  # SUCCESS | RETRYABLE | FATAL
    reasoning: str


# ---------------------------------------------------------------------------
# LangGraph state (TypedDict — must NOT be Pydantic BaseModel)
# ---------------------------------------------------------------------------

class AgentState(TypedDict):
    """
    Complete execution context for a single agent run.
    Carried through every LangGraph node.
    """
    task_id: str
    user_request: str

    # Plan
    plan: List[Dict[str, Any]]          # List of PlanStep dicts
    current_step_index: int

    # Current execution
    current_tool_request: Optional[Dict[str, Any]]  # ToolRequest dict

    # History
    tool_results: List[Dict[str, Any]]
    observations: List[Dict[str, Any]]  # List of Observation dicts

    # Review
    review_verdict: Optional[str]       # SUCCESS | RETRYABLE | FATAL
    review_reasoning: Optional[str]

    # Loop counters (never modifiable by LLM)
    retry_count: int
    replan_count: int
    tool_call_count: int

    # Approval
    pending_approval_id: Optional[str]

    # Terminal state
    task_status: str                    # mirrors TaskStatus enum values
    final_response: Optional[str]
    error: Optional[str]

    # Graph routing signal (set by each node, read by conditional edges)
    next_node: Optional[str]


# ---------------------------------------------------------------------------
# Legacy Pydantic model kept for API response serialisation
# ---------------------------------------------------------------------------

class AgentResponse(BaseModel):
    task_id: str
    status: str
    final_response: Optional[str] = None
    error: Optional[str] = None
