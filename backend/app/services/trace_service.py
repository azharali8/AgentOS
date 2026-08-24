"""
AgentOS Phase 13 — Hierarchical Execution Trace Service.

Assembles detailed execution graphs from persistent events, executions, and protocol messages:
Task
 ├── Task Classification (Risk, Category, Complexity)
 ├── Context Bundle (Files, Rationale, Tokens)
 ├── Agent Executions
 │    ├── LLM / Tool Calls
 │    ├── Patch Generations & Hashes
 │    ├── Test Reports & Errors
 │    └── Review Verdicts
 ├── Replanning & Failure Recovery Events
 ├── Generated Artifacts
 └── Final Summary Metrics
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from backend.app.db.database import get_db_session
from backend.app.db.models import EventModel, ExecutionModel, TaskModel
from backend.app.services.artifact_service import ArtifactService

logger = logging.getLogger("agentos.trace_service")


class TraceStep(BaseModel):
    step_id: str
    tool_name: str
    operation: str
    status: str
    duration_ms: Optional[int] = None
    risk_level: Optional[str] = None
    output_summary: Optional[str] = None
    error: Optional[str] = None


class AgentTraceNode(BaseModel):
    agent: str
    subtask_id: str
    description: str
    status: str
    steps: List[TraceStep] = Field(default_factory=list)
    artifacts: List[str] = Field(default_factory=list)
    duration_seconds: float = 0.0


class ExecutionTrace(BaseModel):
    task_id: str
    instruction: str
    status: str
    created_at: str
    completed_at: Optional[str] = None
    duration_seconds: float = 0.0
    nodes: List[AgentTraceNode] = Field(default_factory=list)
    recovery_events: List[Dict[str, Any]] = Field(default_factory=list)
    artifacts_count: int = 0
    total_steps_executed: int = 0


class TraceService:
    """Builds hierarchical developer execution traces."""

    @classmethod
    def build_trace(cls, task_id: str) -> Optional[ExecutionTrace]:
        with get_db_session() as session:
            task = session.query(TaskModel).filter(TaskModel.task_id == task_id).first()
            if not task:
                return None

            executions = session.query(ExecutionModel).filter(ExecutionModel.task_id == task_id).order_by(ExecutionModel.started_at.asc()).all()
            events = session.query(EventModel).filter(EventModel.task_id == task_id).order_by(EventModel.timestamp.asc()).all()

            # Eagerly extract attributes within active session
            task_id_val = task.task_id
            instruction_val = task.user_request
            status_val = task.status
            created_at_val = task.created_at.isoformat() if task.created_at else ""
            completed_at_val = task.completed_at.isoformat() if task.completed_at else None
            duration = 0.0
            if task.started_at and task.completed_at:
                duration = (task.completed_at - task.started_at).total_seconds()

            exec_data = [
                {
                    "step_id": ex.step_id,
                    "tool_name": ex.tool_name,
                    "operation": ex.operation,
                    "status": ex.status,
                    "duration_ms": ex.duration_ms,
                    "risk_level": ex.risk_level,
                    "output_summary": ex.output_summary,
                    "error": ex.error,
                }
                for ex in executions
            ]
            event_data = [
                {"event_type": ev.event_type, "payload": dict(ev.payload) if ev.payload else {}}
                for ev in events
            ]

        # Group executions by subtask / step
        steps_by_subtask: Dict[str, List[TraceStep]] = {}
        for ex in exec_data:
            st_id = ex["step_id"] or "root"
            if st_id not in steps_by_subtask:
                steps_by_subtask[st_id] = []
            steps_by_subtask[st_id].append(TraceStep(**ex))

        # Identify agent nodes and recovery events from event stream
        nodes: List[AgentTraceNode] = []
        recovery_events: List[Dict[str, Any]] = []
        subtask_map: Dict[str, Dict[str, Any]] = {}

        for ev in event_data:
            if ev["event_type"] == "SUBTASK_CREATED" and isinstance(ev["payload"], dict):
                s_id = ev["payload"].get("subtask_id", "")
                subtask_map[s_id] = ev["payload"]
            elif ev["event_type"] == "REPLAN_TRIGGERED":
                recovery_events.append(ev["payload"])

        for s_id, s_data in subtask_map.items():
            steps = steps_by_subtask.get(s_id, [])
            nodes.append(
                AgentTraceNode(
                    agent=s_data.get("assigned_agent", "unknown"),
                    subtask_id=s_id,
                    description=s_data.get("description", ""),
                    status=s_data.get("status", "COMPLETED"),
                    steps=steps,
                )
            )

        # Count artifacts
        artifacts = ArtifactService.list_by_task(task_id_val)

        return ExecutionTrace(
            task_id=task_id_val,
            instruction=instruction_val,
            status=status_val,
            created_at=created_at_val,
            completed_at=completed_at_val,
            duration_seconds=duration,
            nodes=nodes,
            recovery_events=recovery_events,
            artifacts_count=len(artifacts),
            total_steps_executed=len(exec_data),
        )
