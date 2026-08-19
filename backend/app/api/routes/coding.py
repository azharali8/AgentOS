"""
AgentOS Phase 4 — REST API endpoints for the Autonomous Coding Workflow.
"""

from typing import Any, Dict, Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.app.models.task import TaskResult
from backend.app.services.coding_service import CodingService

router = APIRouter(prefix="/coding", tags=["coding"])


class CodingTaskRequest(BaseModel):
    instruction: str = Field(..., min_length=3, description="Software engineering or debugging instruction.")
    sync: bool = Field(default=False, description="Run synchronously for testing/scripts.")


class CodingApprovalResolution(BaseModel):
    approved: bool = Field(default=True, description="Approve or reject proposed code patch.")


@router.post("/run", response_model=TaskResult)
def run_coding_task(req: CodingTaskRequest) -> TaskResult:
    """Start an autonomous software engineering and debugging task."""
    return CodingService.start_coding_task(instruction=req.instruction, sync=req.sync)


@router.get("/{task_id}")
def get_coding_status(task_id: str) -> Dict[str, Any]:
    """Get current status and phase of a coding workflow task."""
    state = CodingService.get_coding_state(task_id)
    if not state:
        raise HTTPException(status_code=404, detail="Coding task not found")
    return {
        "task_id": task_id,
        "status": state.get("status", "UNKNOWN"),
        "iteration": state.get("iteration", 0),
        "approval_id": state.get("approval_id"),
        "approval_status": state.get("approval_status"),
        "patch_hash": state.get("patch_hash"),
    }


@router.get("/{task_id}/diagnosis")
def get_coding_diagnosis(task_id: str) -> Dict[str, Any]:
    """Get the root-cause diagnosis formulated by the DebuggerAgent."""
    diag = CodingService.get_diagnosis(task_id)
    if not diag:
        raise HTTPException(status_code=404, detail="Diagnosis not available for this task")
    return diag


@router.get("/{task_id}/report")
def get_coding_report(task_id: str) -> Dict[str, Any]:
    """Get the final engineering report for a completed coding task."""
    report = CodingService.get_final_report(task_id)
    if not report:
        raise HTTPException(status_code=404, detail="Report not available for this task")
    return report


@router.post("/{task_id}/resolve", response_model=TaskResult)
def resolve_coding_approval(task_id: str, resolution: CodingApprovalResolution) -> TaskResult:
    """Resolve human approval and resume the autonomous coding workflow."""
    return CodingService.resume_approval(task_id=task_id, approved=resolution.approved)
