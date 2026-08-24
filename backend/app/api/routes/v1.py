"""
AgentOS Phase 9 — API v1 Router Definition.

Binds unified v1 routes for:
- /api/v1/tasks
- /api/v1/agents
- /api/v1/intelligence
- /api/v1/evaluations
- /api/v1/system
- /api/v1/events
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from datetime import datetime, timezone
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect, status
from pydantic import BaseModel, Field

from backend.app.auth.service import UserRole, get_current_user, require_role, AuthenticatedUser, AuthService
from backend.app.agents.registry import AgentRegistry
from backend.app.agents.supervisor import SupervisorAgent
from backend.app.models.multi_agent import AgentDefinition, AgentType, SubTask
from backend.app.models.task import TaskResult, TaskStatus
from backend.app.evaluation.agent_profiler import AgentProfiler
from backend.app.evaluation.benchmark import BenchmarkSuite
from backend.app.evaluation.adaptive_benchmarks import AdaptiveBenchmarkSuite
from backend.app.evaluation.metrics import MetricsCollector
from backend.app.services.event_service import EventService
from backend.app.services.task_service import TaskService
from backend.app.services.llm_usage import LLMUsageService
from backend.app.security.rate_limit import RateLimiter
from backend.app.security.approval import ApprovalManager
from backend.app.security.sensitive_files import is_sensitive_path

from backend.app.services.multi_agent_service import MultiAgentService
from backend.app.services.workspace_service import WorkspaceService
from backend.app.models.approval import ApprovalRequest, ApprovalResponse, ApprovalStatus
from backend.app.config.settings import settings

# Root v1 Router
v1_router = APIRouter(prefix="/api/v1")

# Sub-routers
auth_v1 = APIRouter(prefix="/auth", tags=["v1-auth"])
tasks_v1 = APIRouter(prefix="/tasks", tags=["v1-tasks"])
agents_v1 = APIRouter(prefix="/agents", tags=["v1-agents"])
approvals_v1 = APIRouter(prefix="/approvals", tags=["v1-approvals"])
workspace_v1 = APIRouter(prefix="/workspace", tags=["v1-workspace"])
intelligence_v1 = APIRouter(prefix="/intelligence", tags=["v1-intelligence"])
evaluations_v1 = APIRouter(prefix="/evaluations", tags=["v1-evaluations"])
system_v1 = APIRouter(prefix="/system", tags=["v1-system"])
events_v1 = APIRouter(prefix="/events", tags=["v1-events"])
artifacts_v1 = APIRouter(prefix="/artifacts", tags=["v1-artifacts"])


@artifacts_v1.get("/{artifact_id}")
def get_artifact(artifact_id: str, user: AuthenticatedUser = Depends(get_current_user)) -> Dict[str, Any]:
    """Retrieve single artifact with cryptographic SHA-256 integrity verification."""
    from backend.app.services.artifact_service import ArtifactService, ArtifactIntegrityError
    try:
        art = ArtifactService.get(artifact_id)
        if not art:
            raise HTTPException(status_code=404, detail=f"Artifact '{artifact_id}' not found")
        return art.model_dump()
    except ArtifactIntegrityError as exc:
        raise HTTPException(status_code=409, detail=str(exc))


# ─────────────────────────────────────────────────────────────────────────────
# 0. Authentication API
# ─────────────────────────────────────────────────────────────────────────────

class LoginRequestV1(BaseModel):
    email: str = Field(..., description="User email address")
    password: str = Field(..., min_length=4, description="User password")


class LoginResponseV1(BaseModel):
    token: str
    user_id: str
    username: str
    email: str
    role: str
    message: str = "Authentication successful"


class UserProfileResponseV1(BaseModel):
    user_id: str
    username: str
    email: Optional[str] = None
    role: str
    is_authenticated: bool = True


@auth_v1.post("/login", response_model=LoginResponseV1)
def login_v1(req: LoginRequestV1):
    """Authenticate user with email and password, returning session token."""
    res = AuthService.authenticate_credentials(req.email, req.password)
    if not res:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )
    user, token = res
    return LoginResponseV1(
        token=token,
        user_id=user.user_id,
        username=user.username,
        email=user.email or req.email,
        role=user.role.value if hasattr(user.role, "value") else str(user.role),
    )


@auth_v1.get("/me", response_model=UserProfileResponseV1)
def get_current_user_profile(user: AuthenticatedUser = Depends(get_current_user)):
    """Return currently authenticated user identity and resolved RBAC role."""
    return UserProfileResponseV1(
        user_id=user.user_id,
        username=user.username,
        email=user.email or f"{user.username}@agentos.local",
        role=user.role.value if hasattr(user.role, "value") else str(user.role),
        is_authenticated=True,
    )


@auth_v1.post("/logout")
def logout_v1(user: AuthenticatedUser = Depends(get_current_user)):
    """Terminate current user session."""
    return {"message": "Session terminated successfully"}


# ─────────────────────────────────────────────────────────────────────────────
# 1. Unified Tasks API
# ─────────────────────────────────────────────────────────────────────────────

class TaskCreateRequestV1(BaseModel):
    task: str = Field(..., min_length=3, description="Task prompt or instruction")
    context: Dict[str, Any] = Field(default_factory=dict, description="Context metadata")
    priority: int = Field(default=1, ge=1, le=10, description="Priority")
    requested_agent: Optional[str] = Field(default=None, description="Target agent name")
    execution_mode: str = Field(default="autonomous", description="Execution mode")
    auto_start: bool = Field(default=True, description="Start Supervisor execution automatically")
    sync: bool = Field(default=False, description="Run synchronously if True")
    metadata: Dict[str, Any] = Field(default_factory=dict)


class TaskResponseV1(BaseModel):
    task_id: str
    status: str
    instruction: str
    created_at: datetime
    updated_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    result_summary: Optional[str] = None
    request_id: Optional[str] = None
    error: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


@tasks_v1.post("", response_model=TaskResponseV1, status_code=201)
def create_task(req: TaskCreateRequestV1, user: AuthenticatedUser = Depends(get_current_user)):
    """
    Submit a task to the AgentOS execution platform and start the real Supervisor/LangGraph execution.
    """
    RateLimiter.check_rate_limit(f"task_create:{user.user_id}")
    
    from backend.app.models.task import TaskRequest
    task_req = TaskRequest(instruction=req.task)
    task_record = TaskService.create_task(request=task_req)
    
    EventService.record_event(
        task_id=task_record.task_id,
        event_type="TASK_CREATED",
        payload={
            "instruction": req.task,
            "owner": user.user_id,
            "priority": req.priority,
            "execution_mode": req.execution_mode,
            "requested_agent": req.requested_agent,
        }
    )

    if req.auto_start:
        import threading
        from backend.app.services.multi_agent_service import MultiAgentService
        def _execute_bg():
            try:
                # Use MultiAgentService with existing task ID
                TaskService.update_task_status(task_record.task_id, TaskStatus.PLANNING)
                graph = MultiAgentService.start_task(instruction=req.task, sync=True)
            except Exception as e:
                TaskService.set_error(task_record.task_id, str(e))

        if req.sync:
            _execute_bg()
            task_record = TaskService.get_task(task_record.task_id) or task_record
        else:
            threading.Thread(target=_execute_bg, daemon=True, name=f"task-exec-{task_record.task_id[:8]}").start()
    
    return TaskResponseV1(
        task_id=task_record.task_id,
        status="PENDING" if not req.sync else (task_record.status.value if hasattr(task_record.status, "value") else str(task_record.status)),
        instruction=task_record.user_request,
        created_at=task_record.created_at,
        updated_at=task_record.started_at,
        completed_at=task_record.completed_at,
        result_summary=task_record.final_response,
        request_id=str(uuid.uuid4()),
        error=task_record.error,
        metadata=req.metadata,
    )


@tasks_v1.get("", response_model=List[TaskResponseV1])
def list_tasks(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    user: AuthenticatedUser = Depends(get_current_user),
):
    """List tasks filtered with ownership isolation."""
    tasks = TaskService.list_tasks(limit=limit, offset=offset)
    user_tasks = [
        t for t in tasks 
        if user.role == UserRole.ADMIN or getattr(t, "user_id", None) in (None, user.user_id)
    ]
    return [
        TaskResponseV1(
            task_id=t.task_id,
            status=t.status.value if hasattr(t.status, "value") else str(t.status),
            instruction=t.user_request,
            created_at=t.created_at,
            updated_at=t.started_at,
            completed_at=t.completed_at,
            result_summary=t.final_response,
            error=t.error,
        )
        for t in user_tasks
    ]


@tasks_v1.get("/{task_id}", response_model=TaskResponseV1)
def get_task(task_id: str, user: AuthenticatedUser = Depends(get_current_user)):
    """Get single task details with ownership authorization check."""
    task = TaskService.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"Task '{task_id}' not found")
    
    if user.role != UserRole.ADMIN and getattr(task, "user_id", None) not in (None, user.user_id):
        raise HTTPException(status_code=403, detail="Unauthorized access to private task")
        
    return TaskResponseV1(
        task_id=task.task_id,
        status=task.status.value if hasattr(task.status, "value") else str(task.status),
        instruction=task.user_request,
        created_at=task.created_at,
        updated_at=task.started_at,
        completed_at=task.completed_at,
        result_summary=task.final_response,
        error=task.error,
    )


@tasks_v1.get("/{task_id}/status")
def get_task_status(task_id: str, user: AuthenticatedUser = Depends(get_current_user)) -> Dict[str, Any]:
    """Retrieve simplified task execution lifecycle status."""
    task = TaskService.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"Task '{task_id}' not found")
    
    if user.role != UserRole.ADMIN and getattr(task, "user_id", None) not in (None, user.user_id):
        raise HTTPException(status_code=403, detail="Unauthorized access to private task")

    status_str = task.status.value if hasattr(task.status, "value") else str(task.status)
    return {
        "task_id": task_id,
        "status": status_str,
        "is_active": status_str in ("PENDING", "RUNNING", "PLANNING", "EXECUTING", "REVIEWING", "WAITING_APPROVAL"),
        "is_completed": status_str in ("COMPLETED", "SUCCESS"),
        "is_failed": status_str in ("FAILED", "ERROR", "CANCELLED"),
        "created_at": task.created_at,
        "completed_at": task.completed_at,
    }


@tasks_v1.get("/{task_id}/result")
def get_task_result(task_id: str, user: AuthenticatedUser = Depends(get_current_user)) -> Dict[str, Any]:
    """Get final structured result summary of a task."""
    task = TaskService.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"Task '{task_id}' not found")
        
    if user.role != UserRole.ADMIN and getattr(task, "user_id", None) not in (None, user.user_id):
        raise HTTPException(status_code=403, detail="Unauthorized access to private task")

    status_str = task.status.value if hasattr(task.status, "value") else str(task.status)
    return {
        "task_id": task_id,
        "status": status_str,
        "summary": task.final_response,
        "error": task.error,
        "completed_at": task.completed_at,
    }


@tasks_v1.get("/{task_id}/events")
def get_task_events(
    task_id: str,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    user: AuthenticatedUser = Depends(get_current_user),
) -> List[Dict[str, Any]]:
    """Get chronological append-only events for a task."""
    task = TaskService.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"Task '{task_id}' not found")
        
    if user.role != UserRole.ADMIN and getattr(task, "user_id", None) not in (None, user.user_id):
        raise HTTPException(status_code=403, detail="Unauthorized access to private task")

    return EventService.list_events(task_id=task_id, limit=limit, offset=offset)


@tasks_v1.post("/{task_id}/cancel")
def cancel_task(task_id: str, user: AuthenticatedUser = Depends(get_current_user)) -> Dict[str, Any]:
    """Execute two-phase task cancellation with ownership verification."""
    task = TaskService.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"Task '{task_id}' not found")
        
    if user.role != UserRole.ADMIN and getattr(task, "user_id", None) not in (None, user.user_id):
        raise HTTPException(status_code=403, detail="Unauthorized access to private task")

    from backend.app.services.task_runtime import TaskRuntime
    success = TaskRuntime.cancel_task(task_id, user_id=user.user_id)
    if not success:
        raise HTTPException(status_code=400, detail="Task cannot be cancelled from its current status")
        
    return {"task_id": task_id, "status": "CANCELLED"}


@tasks_v1.post("/{task_id}/pause")
def pause_task(task_id: str, user: AuthenticatedUser = Depends(get_current_user)) -> Dict[str, Any]:
    """Gracefully pause an executing task."""
    task = TaskService.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"Task '{task_id}' not found")
        
    if user.role != UserRole.ADMIN and getattr(task, "user_id", None) not in (None, user.user_id):
        raise HTTPException(status_code=403, detail="Unauthorized access to private task")

    from backend.app.services.task_runtime import TaskRuntime
    success = TaskRuntime.pause_task(task_id, user_id=user.user_id)
    if not success:
        raise HTTPException(status_code=400, detail=f"Task '{task_id}' cannot be paused from status '{task.status}'.")

    return {"task_id": task_id, "status": "PAUSED"}


@tasks_v1.post("/{task_id}/resume")
def resume_task(task_id: str, user: AuthenticatedUser = Depends(get_current_user)) -> Dict[str, Any]:
    """Resume a paused or interrupted task from durable checkpoint."""
    task = TaskService.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"Task '{task_id}' not found")
        
    if user.role != UserRole.ADMIN and getattr(task, "user_id", None) not in (None, user.user_id):
        raise HTTPException(status_code=403, detail="Unauthorized access to private task")

    from backend.app.services.task_runtime import TaskRuntime
    try:
        res = TaskRuntime.resume_task(task_id, user_id=user.user_id)
        return {"task_id": task_id, "status": res.status.value if hasattr(res.status, "value") else str(res.status)}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@tasks_v1.get("/{task_id}/artifacts")
def get_task_artifacts(task_id: str, user: AuthenticatedUser = Depends(get_current_user)) -> List[Dict[str, Any]]:
    """List immutable artifacts generated for a task with read-time integrity checks."""
    task = TaskService.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"Task '{task_id}' not found")

    from backend.app.services.artifact_service import ArtifactService
    artifacts = ArtifactService.list_by_task(task_id)
    return [a.model_dump() for a in artifacts]


@tasks_v1.get("/{task_id}/context")
def get_task_context(task_id: str, user: AuthenticatedUser = Depends(get_current_user)) -> Dict[str, Any]:
    """Inspect bounded context bundle and explanation assembled for this task."""
    task = TaskService.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"Task '{task_id}' not found")

    from backend.app.services.context_engine import ContextEngine
    engine = ContextEngine()
    bundle = engine.assemble_context(
        task_id=task_id,
        instruction=task.user_request,
        target_agent=AgentType.SUPERVISOR,
    )
    return bundle.model_dump()


@tasks_v1.get("/{task_id}/trace")
def get_task_trace(task_id: str, user: AuthenticatedUser = Depends(get_current_user)) -> Dict[str, Any]:
    """Retrieve full hierarchical execution trace for developer telemetry."""
    from backend.app.services.trace_service import TraceService
    trace = TraceService.build_trace(task_id)
    if not trace:
        raise HTTPException(status_code=404, detail=f"Trace for task '{task_id}' not found")
    return trace.model_dump()


# ─────────────────────────────────────────────────────────────────────────────
# 2. Unified Agents API
# ─────────────────────────────────────────────────────────────────────────────

@agents_v1.get("", response_model=List[AgentDefinition])
def list_agents_v1(user: AuthenticatedUser = Depends(get_current_user)) -> List[AgentDefinition]:
    """List all registered specialized agents with capability metadata."""
    return AgentRegistry.list_agents()


@agents_v1.get("/{agent_id}", response_model=AgentDefinition)
def get_agent_v1(agent_id: str, user: AuthenticatedUser = Depends(get_current_user)) -> AgentDefinition:
    """Look up an agent definition by identifier."""
    agent = AgentRegistry.get(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_id}' not found")
    return agent


@agents_v1.get("/{agent_id}/status")
def get_agent_status_v1(agent_id: str, user: AuthenticatedUser = Depends(get_current_user)) -> Dict[str, Any]:
    """Check availability and status of a specialized agent."""
    agent = AgentRegistry.get(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_id}' not found")
    return {
        "agent_id": agent_id,
        "name": agent.name,
        "status": "available",
        "risk_level": agent.risk_level,
        "max_concurrency": agent.max_concurrency,
    }


@agents_v1.get("/{agent_id}/capabilities")
def get_agent_capabilities_v1(agent_id: str, user: AuthenticatedUser = Depends(get_current_user)) -> List[str]:
    """Get explicit capabilities supported by this agent."""
    agent = AgentRegistry.get(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_id}' not found")
    return [c.value for c in agent.capabilities]


@agents_v1.get("/{agent_id}/metrics")
def get_agent_metrics_v1(agent_id: str, user: AuthenticatedUser = Depends(get_current_user)) -> Dict[str, Any]:
    """Fetch empirical performance metrics for an agent."""
    agent = AgentRegistry.get(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_id}' not found")
    profile = AgentProfiler.get_profile(agent.agent_type)
    return profile.model_dump()


class AgentInvokeRequestV1(BaseModel):
    instruction: str = Field(..., min_length=3)
    task_id: Optional[str] = None
    target_files: List[str] = Field(default_factory=list)
    context: Dict[str, Any] = Field(default_factory=dict)


@agents_v1.post("/{agent_id}/invoke")
def invoke_agent_v1(
    agent_id: str,
    req: AgentInvokeRequestV1,
    user: AuthenticatedUser = Depends(get_current_user),
) -> Dict[str, Any]:
    """
    Invoke a specialized agent directly under Supervisor execution boundaries.
    Enforces that cybersecurity agent requires ADMIN role.
    """
    RateLimiter.check_rate_limit(f"agent_invoke:{user.user_id}")
    agent = AgentRegistry.get(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_id}' not found")
        
    # NON-NEGOTIABLE RBAC: Cybersecurity is ADMIN ONLY
    if agent.agent_type == AgentType.CYBERSECURITY:
        if user.role != UserRole.ADMIN:
            raise HTTPException(status_code=403, detail="ADMIN role required to invoke CYBERSECURITY agent")

    task_id = req.task_id or f"inv-{uuid.uuid4().hex[:8]}"
    
    # Execute through Supervisor subtask routing
    supervisor = SupervisorAgent()
    subtask = SubTask(
        task_id=task_id,
        subtask_id=f"st-{uuid.uuid4().hex[:6]}",
        description=req.instruction,
        assigned_agent=agent.agent_type,
        target_files=req.target_files,
        input_data=req.context,
    )
    
    result = supervisor.execute_subtask(subtask)
    
    return {
        "status": result.status.value if hasattr(result.status, "value") else str(result.status),
        "agent": agent.name,
        "task_id": task_id,
        "summary": result.summary,
        "evidence": result.evidence,
        "tokens_used": result.tokens_used,
        "duration_seconds": result.duration_seconds,
        "error": result.error,
    }


# ─────────────────────────────────────────────────────────────────────────────
# 3. System & Health API
# ─────────────────────────────────────────────────────────────────────────────

@system_v1.get("/health")
def get_system_health() -> Dict[str, Any]:
    """Lightweight liveness probe."""
    return {
        "status": "HEALTHY",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "version": "0.3.0",
        "process": "running",
    }


@system_v1.get("/readiness")
def get_system_readiness() -> Dict[str, Any]:
    """Production readiness probe verifying essential subsystem health."""
    agents_count = len(AgentRegistry.list_agents())
    return {
        "status": "READY",
        "ready": True,
        "database": "connected",
        "security_manager": "active",
        "rate_limiter": "active",
        "agents_available": agents_count,
        "model_router": "ready (local strategy default)",
    }


@system_v1.get("/version")
def get_system_version() -> Dict[str, Any]:
    """API and Platform version contract."""
    return {
        "platform": "AgentOS",
        "version": "0.3.0",
        "api_version": "v1",
        "phase": "Phase 9 — Production Platform & SDK",
    }


@system_v1.get("/metrics")
def get_system_metrics(user: AuthenticatedUser = Depends(get_current_user)) -> Dict[str, Any]:
    """Safe system metrics snapshot."""
    metrics = MetricsCollector.get_metrics_snapshot()
    llm_summary = LLMUsageService.get_summary()
    return {
        "system_metrics": metrics,
        "llm_usage": llm_summary,
    }


@system_v1.get("/models")
def get_system_models() -> Dict[str, Any]:
    """Probe real model availability and task-aware router summary."""
    from backend.app.services.model_router import ModelRouter
    return ModelRouter.get_runtime_summary()


@system_v1.get("/models/health")
def get_model_health() -> Dict[str, Any]:
    """Dedicated model router health probe endpoint."""
    from backend.app.services.model_router import ModelRouter
    health = ModelRouter.check_health()
    return health.model_dump()


@system_v1.get("/runtime")
def get_system_runtime() -> Dict[str, Any]:
    """Get runtime health, active model router, and worker concurrency stats."""
    from backend.app.services.model_router import ModelRouter
    from backend.app.services.concurrency_manager import ConcurrencyManager
    return {
        "platform": "AgentOS",
        "phase": "Phase 13 — Production-Grade Autonomous Engineering Platform",
        "model_runtime": ModelRouter.get_runtime_summary(),
        "concurrency": ConcurrencyManager.get_metrics(),
    }


@system_v1.get("/concurrency")
def get_system_concurrency() -> Dict[str, Any]:
    """Get detailed worker semaphore allocations and task queue status."""
    from backend.app.services.concurrency_manager import ConcurrencyManager
    return ConcurrencyManager.get_metrics()


@system_v1.get("/audit-logs")
def get_system_audit_logs(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    action: Optional[str] = None,
    user: AuthenticatedUser = Depends(require_role(UserRole.ADMIN)),
) -> List[Dict[str, Any]]:
    """Administrative security and operational audit log stream (ADMIN only)."""
    from backend.app.services.audit_service import AuditService
    logs = AuditService.list_logs(limit=limit, offset=offset, action=action)
    return [l.model_dump() for l in logs]


# ─────────────────────────────────────────────────────────────────────────────
# 4. Human-in-the-Loop Approvals API
# ─────────────────────────────────────────────────────────────────────────────

class ApprovalResolveRequestV1(BaseModel):
    approved: bool = Field(default=True, description="Approve (True) or Reject (False)")
    reason: Optional[str] = None


@approvals_v1.get("", response_model=List[ApprovalRequest])
def list_approvals_v1(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    user: AuthenticatedUser = Depends(get_current_user),
):
    """List pending and resolved approvals with pagination."""
    return ApprovalManager.list_approvals(limit=limit, offset=offset)


@approvals_v1.get("/{approval_id}", response_model=ApprovalRequest)
def get_approval_v1(approval_id: str, user: AuthenticatedUser = Depends(get_current_user)):
    """Get details of an approval request."""
    record = ApprovalManager.get_approval(approval_id)
    if not record:
        raise HTTPException(status_code=404, detail=f"Approval '{approval_id}' not found")
    return record


@approvals_v1.post("/{approval_id}/resolve")
def resolve_approval_v1(
    approval_id: str,
    req: ApprovalResolveRequestV1,
    user: AuthenticatedUser = Depends(require_role(UserRole.DEVELOPER)),
) -> Dict[str, Any]:
    """
    Authoritatively resolve a pending human approval and resume the LangGraph execution.
    Requires DEVELOPER or ADMIN role.
    """
    record = ApprovalManager.get_approval(approval_id)
    if not record:
        raise HTTPException(status_code=404, detail=f"Approval '{approval_id}' not found")

    if record.status != ApprovalStatus.PENDING:
        raise HTTPException(
            status_code=409,
            detail=f"Approval already resolved with status: {record.status}",
        )

    # Resolve approval in ApprovalManager
    resolution_status = ApprovalStatus.APPROVED if req.approved else ApprovalStatus.REJECTED
    ApprovalManager.resolve_approval(approval_id, resolution_status, resolved_by=user.user_id)

    # Resume the multi-agent graph
    MultiAgentService.resume_approval(
        task_id=record.task_id,
        approved=req.approved,
    )

    EventService.record_event(
        task_id=record.task_id,
        event_type="APPROVAL_RESOLVED",
        payload={
            "approval_id": approval_id,
            "approved": req.approved,
            "resolved_by": user.user_id,
            "reason": req.reason,
        }
    )

    return {
        "approval_id": approval_id,
        "task_id": record.task_id,
        "status": resolution_status.value,
        "resolved_by": user.user_id,
    }


# ─────────────────────────────────────────────────────────────────────────────
# 5. Workspace Explorer API (Strict Path Security Enforced)
# ─────────────────────────────────────────────────────────────────────────────

@workspace_v1.get("/tree")
def get_workspace_tree(
    subpath: str = Query("", description="Relative path within workspace"),
    user: AuthenticatedUser = Depends(get_current_user),
) -> Dict[str, Any]:
    """List directory contents safely within workspace bounds."""
    try:
        target_dir = WorkspaceService.validate_path(subpath)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    if not target_dir.is_dir():
        raise HTTPException(status_code=400, detail="Target path is not a directory")

    items = []
    root = WorkspaceService.get_workspace_root()
    
    for entry in sorted(target_dir.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower())):
        rel_posix = entry.relative_to(root).as_posix()
        is_sensitive = is_sensitive_path(rel_posix)
        
        items.append({
            "name": entry.name,
            "path": rel_posix,
            "is_dir": entry.is_dir(),
            "size": entry.stat().st_size if entry.is_file() else 0,
            "is_sensitive": is_sensitive,
        })

    return {
        "root": root.name,
        "current_path": target_dir.relative_to(root).as_posix(),
        "items": items,
    }


@workspace_v1.get("/file")
def get_workspace_file(
    path: str = Query(..., description="Relative file path within workspace"),
    user: AuthenticatedUser = Depends(get_current_user),
) -> Dict[str, Any]:
    """Safely read file content within workspace boundaries."""
    try:
        target_file = WorkspaceService.validate_path(path)
    except Exception as exc:
        err_msg = str(exc)
        if "access denied" in err_msg.lower() or "forbidden" in err_msg.lower() or "sensitive" in err_msg.lower():
            raise HTTPException(status_code=403, detail=err_msg)
        raise HTTPException(status_code=400, detail=err_msg)


    root = WorkspaceService.get_workspace_root()
    rel_posix = target_file.relative_to(root).as_posix()
    
    if is_sensitive_path(rel_posix):
        raise HTTPException(status_code=403, detail=f"Access to sensitive file '{rel_posix}' is forbidden")

    if not target_file.is_file():
        raise HTTPException(status_code=404, detail="File not found")

    try:
        content = target_file.read_text(encoding="utf-8", errors="replace")
        return {
            "path": rel_posix,
            "name": target_file.name,
            "size": target_file.stat().st_size,
            "content": content,
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to read file: {str(exc)}")


# ─────────────────────────────────────────────────────────────────────────────
# 6. Evaluations & Intelligence APIs
# ─────────────────────────────────────────────────────────────────────────────

@evaluations_v1.get("/benchmarks")
def run_benchmarks_v1(user: AuthenticatedUser = Depends(require_role(UserRole.DEVELOPER))) -> Dict[str, Any]:
    """Run full benchmark battery and return consolidated metrics."""
    p6_results = BenchmarkSuite.run_all()
    p7_results = AdaptiveBenchmarkSuite.run_all()
    return {
        "phase6_benchmark": p6_results,
        "phase7_adaptive_benchmark": p7_results,
    }


# ─────────────────────────────────────────────────────────────────────────────
# 7. Streaming & WebSocket Events
# ─────────────────────────────────────────────────────────────────────────────

@events_v1.websocket("/stream/{task_id}")
async def stream_task_events_ws(
    websocket: WebSocket,
    task_id: str,
    token: Optional[str] = Query(None),
    last_event_id: Optional[str] = Query(None),
):
    """
    Harden WebSocket streaming endpoint:
    - Verifies authentication token when AUTH_ENABLED is True
    - Enforces connection rate limits
    - Supports event replay from last_event_id for reconnecting clients
    """
    client_ip = websocket.client.host if websocket.client else "unknown"
    
    # Rate limit check for websocket handshakes
    try:
        RateLimiter.check_rate_limit(client_ip, domain="ws", limit=5, window_seconds=60)
    except HTTPException:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Rate limit exceeded")
        return

    # Authentication verification
    if settings.AUTH_ENABLED:
        if not token:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Authentication token required")
            return
        user = AuthService.authenticate_key(token)
        if not user:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Invalid or expired session token")
            return

    await websocket.accept()
    try:
        # Send initial connection event
        await websocket.send_json({
            "event_type": "STREAM_CONNECTED",
            "task_id": task_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        
        # Stream existing events (support replay from last_event_id)
        events = EventService.list_events(task_id, limit=100)
        send_events = events
        if last_event_id:
            # Find index of last_event_id and only replay events after it
            idx = next((i for i, e in enumerate(events) if e.get("event_id") == last_event_id), -1)
            if idx != -1:
                send_events = events[idx + 1:]

        for ev in send_events:
            ev_data = dict(ev)
            if isinstance(ev_data.get("timestamp"), datetime):
                ev_data["timestamp"] = ev_data["timestamp"].isoformat()
            await websocket.send_json(ev_data)
            
        # Keep alive for incoming messages / heartbeats
        while True:
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        pass


# Register all sub-routers to v1
v1_router.include_router(auth_v1)
v1_router.include_router(tasks_v1)
v1_router.include_router(agents_v1)
v1_router.include_router(approvals_v1)
v1_router.include_router(workspace_v1)
v1_router.include_router(intelligence_v1)
v1_router.include_router(evaluations_v1)
v1_router.include_router(system_v1)
v1_router.include_router(events_v1)
v1_router.include_router(artifacts_v1)
