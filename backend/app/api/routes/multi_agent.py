"""
AgentOS Phase 5 — Multi-Agent REST API Endpoints.
"""

from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException, Depends
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

@agents_router.get("/registry", response_model=List[AgentDefinition])
def get_registry() -> List[AgentDefinition]:
    return AgentRegistry.list_agents()

@agents_router.get("/available", response_model=List[AgentDefinition])
def get_available_agents() -> List[AgentDefinition]:
    # In a full impl, this might filter disabled agents.
    return AgentRegistry.list_agents()


@agents_router.get("/{name}", response_model=AgentDefinition)
def get_agent(name: str) -> AgentDefinition:
    agent = AgentRegistry.get(name)
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent '{name}' not found")
    return agent


@agents_router.get("/{name}/status")
def get_agent_status(name: str) -> Dict[str, Any]:
    agent = AgentRegistry.get(name)
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent '{name}' not found")
    return {"status": "READY"}


@agents_router.get("/{name}/capabilities")
def get_agent_capabilities(name: str) -> List[str]:
    agent = AgentRegistry.get(name)
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent '{name}' not found")
    return [c.value for c in agent.capabilities]


from backend.app.evaluation.agent_profiler import AgentProfiler

@agents_router.get("/{name}/metrics")
def get_agent_metrics(name: str) -> Dict[str, Any]:
    agent = AgentRegistry.get(name)
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent '{name}' not found")
    profile = AgentProfiler.get_profile(agent.agent_type)
    return profile.model_dump()


from backend.app.auth.service import UserRole, get_current_user

@agents_router.post("/{name}/invoke")
def invoke_agent(name: str, payload: Dict[str, Any], user=Depends(get_current_user)) -> Dict[str, Any]:
    agent = AgentRegistry.get(name)
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent '{name}' not found")
        
    if agent.agent_type == AgentType.CYBERSECURITY:
        if user.role != UserRole.ADMIN:
            raise HTTPException(status_code=403, detail="ADMIN role required to invoke CYBERSECURITY agent")
            
    # For Phase 8, we just mock the invocation return structure to prove routing integration.
    # True specialized invocation goes through Supervisor and LangGraph.
    return {
        "status": "INVOKED",
        "agent": agent.name,
        "task_id": payload.get("task_id", "t-test")
    }

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
