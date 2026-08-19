from typing import List, Optional
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from backend.app.models.approval import ApprovalRequest, ApprovalResponse, ApprovalStatus
from backend.app.models.task import TaskResult
from backend.app.security.approval import ApprovalManager
from backend.app.services.agent_service import AgentService

router = APIRouter()


class ApprovalResolution(BaseModel):
    status: ApprovalStatus
    reason: Optional[str] = None


@router.get("", response_model=List[ApprovalRequest])
def list_approvals(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    """List pending and resolved approvals with pagination."""
    return ApprovalManager.list_approvals(limit=limit, offset=offset)


@router.get("/{approval_id}", response_model=ApprovalRequest)
def get_approval(approval_id: str):
    """Get details of an approval request."""
    record = ApprovalManager.get_approval(approval_id)
    if not record:
        raise HTTPException(status_code=404, detail="Approval not found")
    return record


@router.post("/{approval_id}/resolve", response_model=TaskResult)
def resolve_approval(approval_id: str, resolution: ApprovalResolution):
    """
    Resolve a pending approval (APPROVED or REJECTED) and resume the agent graph.
    """
    record = ApprovalManager.get_approval(approval_id)
    if not record:
        raise HTTPException(status_code=404, detail="Approval not found")

    if record.status != ApprovalStatus.PENDING:
        raise HTTPException(
            status_code=409,
            detail=f"Approval already resolved with status: {record.status}",
        )

    approved = resolution.status == ApprovalStatus.APPROVED
    task_id = record.task_id

    result = AgentService.resolve_approval(
        task_id=task_id,
        approval_id=approval_id,
        approved=approved,
    )
    if not result:
        raise HTTPException(status_code=404, detail="Task not found")

    return result
