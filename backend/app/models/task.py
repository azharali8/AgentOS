from pydantic import BaseModel, Field
from typing import List, Optional, Any
from datetime import datetime
from enum import Enum

class TaskStatus(str, Enum):
    PENDING = "PENDING"
    PLANNING = "PLANNING"
    WAITING_APPROVAL = "WAITING_APPROVAL"
    EXECUTING = "EXECUTING"
    PAUSED = "PAUSED"
    REVIEWING = "REVIEWING"
    CANCELLING = "CANCELLING"
    CANCELLED = "CANCELLED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    RECOVERY_REQUIRED = "RECOVERY_REQUIRED"

class TaskPriority(str, Enum):
    LOW = "LOW"
    NORMAL = "NORMAL"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"

class TaskRequest(BaseModel):
    instruction: str
    priority: TaskPriority = TaskPriority.NORMAL
    timeout_seconds: Optional[int] = None
    max_retries: Optional[int] = None

class TaskResult(BaseModel):
    task_id: str
    user_request: str
    status: TaskStatus
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    current_step: int = 0
    total_steps: int = 0
    retry_count: int = 0
    replan_count: int = 0
    final_response: Optional[str] = None
    error: Optional[str] = None
    thread_id: Optional[str] = None
    approval_id: Optional[str] = None
    metadata: Optional[Any] = None
