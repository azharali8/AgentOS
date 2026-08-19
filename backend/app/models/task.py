from pydantic import BaseModel
from typing import List, Optional, Any
from datetime import datetime
from enum import Enum

class TaskStatus(str, Enum):
    PENDING = "PENDING"
    PLANNING = "PLANNING"
    WAITING_APPROVAL = "WAITING_APPROVAL"
    EXECUTING = "EXECUTING"
    REVIEWING = "REVIEWING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    RECOVERY_REQUIRED = "RECOVERY_REQUIRED"

class TaskRequest(BaseModel):
    instruction: str

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

