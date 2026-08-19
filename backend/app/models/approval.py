from pydantic import BaseModel
from typing import Dict, Any, Optional
from datetime import datetime, timezone
from enum import Enum
from backend.app.models.tool import RiskLevel

class ApprovalStatus(str, Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"

class ApprovalRequest(BaseModel):
    approval_id: str
    task_id: str
    step_id: str
    tool_name: str
    operation: str
    arguments_hash: str
    arguments_summary: Dict[str, Any]
    risk_level: RiskLevel
    reason: str
    status: ApprovalStatus = ApprovalStatus.PENDING
    created_at: datetime = datetime.now(timezone.utc)
    resolved_at: Optional[datetime] = None
    resolved_by: Optional[str] = None

class ApprovalResponse(BaseModel):
    approval_id: str
    status: ApprovalStatus
    reason: Optional[str] = None
