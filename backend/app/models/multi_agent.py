"""
AgentOS Phase 5 — Multi-Agent Collaboration Data Models.

Provides strongly typed Pydantic models for specialized agents, supervisor delegation,
subtask decomposition, structured message passing, per-agent budgeting, and execution tracing.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class AgentType(str, Enum):
    SUPERVISOR = "supervisor"
    RESEARCH = "research"
    CODING = "coding"
    DEBUGGER = "debugger"
    REVIEWER = "reviewer"
    DOCUMENTATION = "documentation"
    SECURITY = "security"


class AgentStatus(str, Enum):
    IDLE = "idle"
    PLANNING = "planning"
    RUNNING = "running"
    WAITING = "waiting"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMEOUT = "timeout"


class AgentCapability(str, Enum):
    DECOMPOSITION = "decomposition"
    DELEGATION = "delegation"
    SUPERVISION = "supervision"
    CODE_SEARCH = "code_search"
    CODE_READ = "code_read"
    CODE_SYMBOLS = "code_symbols"
    GIT_READ = "git_read"
    PATCH_APPLY = "patch_apply"
    TEST_RUN = "test_run"
    REVIEW = "review"
    DOCUMENTATION = "documentation"
    SECURITY_INSPECTION = "security_inspection"
    POLICY_EVALUATION = "policy_evaluation"


class AgentBudget(BaseModel):
    max_tokens: int = Field(default=100000, description="Max cumulative tokens allowed")
    max_tool_calls: int = Field(default=50, description="Max allowed tool invocations")
    max_execution_time: int = Field(default=300, description="Max allowed execution seconds")
    max_retries: int = Field(default=3, description="Max retry attempts")
    max_subtasks: int = Field(default=20, description="Max subtasks allowed in a single request")
    max_depth: int = Field(default=5, description="Max nested delegation depth")


class AgentPermission(BaseModel):
    agent_type: AgentType
    allowed_tools: List[str] = Field(default_factory=list, description="Explicitly allowed tool operations")
    can_delegate: bool = Field(default=False, description="Whether agent can spawn subtasks/handoffs")
    can_modify_code: bool = Field(default=False, description="Whether agent can propose or apply code mutations")
    can_execute_tests: bool = Field(default=False, description="Whether agent can trigger test executions")
    allowed_memory_categories: List[str] = Field(default_factory=lambda: ["short_term", "project"])


class AgentDefinition(BaseModel):
    name: str
    agent_type: AgentType
    description: str
    capabilities: List[AgentCapability] = Field(default_factory=list)
    allowed_tools: List[str] = Field(default_factory=list)
    risk_level: str = Field(default="LOW")
    max_concurrency: int = Field(default=1)
    max_execution_time: int = Field(default=300)
    model_config_dict: Dict[str, Any] = Field(default_factory=dict)


class TaskDependency(BaseModel):
    subtask_id: str
    depends_on_id: str


class SubTask(BaseModel):
    task_id: str
    parent_task_id: Optional[str] = None
    subtask_id: str
    description: str
    assigned_agent: AgentType
    dependencies: List[str] = Field(default_factory=list, description="List of subtask_ids that must complete first")
    priority: int = Field(default=1, description="Scheduling priority (higher executes earlier)")
    status: AgentStatus = Field(default=AgentStatus.IDLE)
    input_data: Dict[str, Any] = Field(default_factory=dict)
    output_data: Optional[Dict[str, Any]] = None
    target_files: List[str] = Field(default_factory=list, description="Target files for mutation/analysis")
    error: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None


class AgentMessage(BaseModel):
    message_id: str
    task_id: str
    sender_agent: AgentType
    recipient_agent: AgentType
    message_type: str = Field(default="INFO", description="TASK_ASSIGNMENT | STATUS_UPDATE | RESULT | QUERY | ERROR")
    payload: Dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    correlation_id: Optional[str] = None


class AgentResult(BaseModel):
    subtask_id: str
    agent_type: AgentType
    status: AgentStatus
    summary: str
    evidence: Dict[str, Any] = Field(default_factory=dict)
    files_modified: List[str] = Field(default_factory=list)
    tokens_used: int = 0
    duration_seconds: float = 0.0
    error: Optional[str] = None


class AgentAssignment(BaseModel):
    assignment_id: str
    task_id: str
    subtask_id: str
    agent_type: AgentType
    assigned_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    status: AgentStatus = Field(default=AgentStatus.RUNNING)


class AgentExecution(BaseModel):
    execution_id: str
    task_id: str
    subtask_id: str
    agent_type: AgentType
    started_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: Optional[datetime] = None
    duration_seconds: float = 0.0
    status: AgentStatus = Field(default=AgentStatus.RUNNING)
    tokens_used: int = 0
    tool_calls_count: int = 0
    error: Optional[str] = None


class AgentHandoff(BaseModel):
    handoff_id: str
    task_id: str
    from_agent: AgentType
    to_agent: AgentType
    reason: str
    payload: Dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
