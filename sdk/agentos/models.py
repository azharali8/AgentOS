"""
AgentOS Phase 9 — Python SDK Data Models.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class TaskCreateRequest(BaseModel):
    task: str = Field(..., min_length=3, description="Task prompt or instruction")
    context: Dict[str, Any] = Field(default_factory=dict, description="Execution context metadata")
    priority: int = Field(default=1, ge=1, le=10, description="Task scheduling priority")
    requested_agent: Optional[str] = Field(default=None, description="Optional target specialized agent")
    execution_mode: str = Field(default="autonomous", description="Execution mode: autonomous | supervised")
    metadata: Dict[str, Any] = Field(default_factory=dict)


class TaskResponse(BaseModel):
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


class TaskStatusResponse(BaseModel):
    task_id: str
    status: str
    is_active: bool
    is_completed: bool
    is_failed: bool
    subtasks_count: int = 0
    completed_count: int = 0
    duration_seconds: float = 0.0


class TaskResultResponse(BaseModel):
    task_id: str
    status: str
    summary: Optional[str] = None
    files_modified: List[str] = Field(default_factory=list)
    tokens_used: int = 0
    duration_seconds: float = 0.0
    error: Optional[str] = None
    evidence: Dict[str, Any] = Field(default_factory=dict)


class TaskEvent(BaseModel):
    event_id: str
    task_id: str
    event_type: str
    timestamp: datetime
    step_id: Optional[str] = None
    payload: Dict[str, Any] = Field(default_factory=dict)


class AgentMetadata(BaseModel):
    agent_id: str
    name: str
    domain: str
    description: str
    capabilities: List[str] = Field(default_factory=list)
    allowed_tools: List[str] = Field(default_factory=list)
    required_role: str = "USER"
    status: str = "available"
    risk_level: str = "LOW"
    max_concurrency: int = 1
    max_execution_time: int = 300


class AgentInvokeRequest(BaseModel):
    instruction: str
    task_id: Optional[str] = None
    context: Dict[str, Any] = Field(default_factory=dict)
    target_files: List[str] = Field(default_factory=list)


class AgentInvokeResponse(BaseModel):
    status: str
    agent: str
    task_id: str
    summary: Optional[str] = None
    evidence: Dict[str, Any] = Field(default_factory=dict)


class SystemHealthResponse(BaseModel):
    status: str
    timestamp: datetime
    version: str = "0.3.0"
    uptime_seconds: float = 0.0


class SystemReadinessResponse(BaseModel):
    status: str
    database: str = "connected"
    security_manager: str = "active"
    model_router: str = "ready"
    rate_limiter: str = "active"
    agents_ready: int = 0
    ready: bool = True
