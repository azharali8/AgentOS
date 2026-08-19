"""
AgentOS Phase 5 — Multi-Agent REST API Endpoints.
"""

from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.app.models.multi_agent import AgentDefinition, AgentType
from backend.app.models.task import TaskResult
from backend.app.agents.registry import AgentRegistry
from backend.app.services.agent_message_bus import AgentMessageBus
from backend.app.services.multi_agent_service import MultiAgentService

agents_router = APIRouter(prefix="/agents", tags=["agents"])
multi_agent_router = APIRouter(prefix="/multi-agent", tags=["multi-agent"])


class MultiAgentRunRequest(BaseModel):
    instruction: str = Field(..., min_length=3, description="Multi-agent instruction")
    sync: bool = Field(default=False, description="Run synchronously")


class ApprovalResolution(BaseModel):
    approved: bool = Field(default=True)


# ── Agent Registry Endpoints ──────────────────────────────────────────

@agents_router.get("", response_model=List[AgentDefinition])
def list_agents() -> List[AgentDefinition]:
    return AgentRegistry.list_agents()


@agents_router.get("/{name}", response_model=AgentDefinition)
def get_agent(name: str) -> AgentDefinition:
    agent = AgentRegistry.get(name)
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent '{name}' not found")
    return agent


@agents_router.post("/register", response_model=AgentDefinition)
def register_agent(agent_def: AgentDefinition) -> AgentDefinition:
    try:
        AgentRegistry.register(agent_def)
        return agent_def
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


# ── Multi-Agent Execution Endpoints ───────────────────────────────────

@multi_agent_router.post("/run", response_model=TaskResult)
def run_multi_agent_task(req: MultiAgentRunRequest) -> TaskResult:
    return MultiAgentService.start_task(instruction=req.instruction, sync=req.sync)


@multi_agent_router.get("/{task_id}")
def get_task_status(task_id: str) -> Dict[str, Any]:
    state = MultiAgentService.get_state(task_id)
    if not state:
        raise HTTPException(status_code=404, detail="Multi-agent task not found")
    return {
        "task_id": task_id,
        "status": state.get("status", "UNKNOWN"),
        "subtasks_count": len(state.get("subtasks", [])),
        "completed_count": len(state.get("completed_subtask_ids", [])),
        "approval_id": state.get("approval_id"),
        "approval_status": state.get("approval_status"),
    }


@multi_agent_router.get("/{task_id}/subtasks")
def get_task_subtasks(task_id: str) -> List[Dict[str, Any]]:
    state = MultiAgentService.get_state(task_id)
    if not state:
        raise HTTPException(status_code=404, detail="Task not found")
    return state.get("subtasks", [])


@multi_agent_router.get("/{task_id}/messages")
def get_task_messages(task_id: str) -> List[Dict[str, Any]]:
    history = AgentMessageBus.get_history(task_id)
    return [m.model_dump() for m in history]


@multi_agent_router.get("/{task_id}/report")
def get_task_report(task_id: str) -> Dict[str, Any]:
    report = MultiAgentService.get_report(task_id)
    if not report:
        raise HTTPException(status_code=404, detail="Report not available")
    return report


@multi_agent_router.post("/{task_id}/resolve", response_model=TaskResult)
def resolve_approval(task_id: str, res: ApprovalResolution) -> TaskResult:
    return MultiAgentService.resume_approval(task_id=task_id, approved=res.approved)
