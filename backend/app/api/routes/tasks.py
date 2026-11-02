from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from datetime import datetime

from backend.app.auth.service import AuthenticatedUser, get_current_user, UserRole
from backend.app.config.settings import settings
from backend.app.models.task import TaskResult
from backend.app.services.event_service import EventService
from backend.app.services.project_service import ProjectService
from backend.app.services.task_service import TaskService

router = APIRouter()


class TaskEventResponse(BaseModel):
    event_id: str
    task_id: str
    event_type: str
    timestamp: datetime
    step_id: Optional[str] = None
    payload: Optional[dict] = None


def _require_task_owner(task_id: str, user: AuthenticatedUser) -> TaskResult:
    """Resolve a task and enforce ownership for project-scoped API access.

    In authenticated mode, legacy tasks without project membership remain
    hidden from non-admin users. In development mode authentication is
    deliberately disabled, so the legacy API retains its pre-project behavior.
    """
    scope = ProjectService.task_scope(task_id, user.user_id)
    if not scope and settings.AUTH_ENABLED and user.role != UserRole.ADMIN:
        raise HTTPException(status_code=404, detail="Task not found")
    task = TaskService.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    if settings.AUTH_ENABLED and scope and user.role != UserRole.ADMIN:
        if scope.get("owner_id") and scope["owner_id"] != user.user_id:
            raise HTTPException(status_code=404, detail="Task not found")
    return task


@router.get("", response_model=List[TaskResult])
def list_tasks(
    limit: int = Query(20, ge=1, le=100, description="Max number of tasks to return"),
    offset: int = Query(0, ge=0, description="Offset from start"),
    user: AuthenticatedUser = Depends(get_current_user),
):
    """List tasks visible to the current user, preserving legacy dev behavior."""
    if not settings.AUTH_ENABLED:
        return TaskService.list_tasks(limit=limit, offset=offset)

    # Filter before paginating so that pages contain the requested number of
    # visible records rather than being shortened by another user's tasks.
    tasks = TaskService.list_tasks(limit=100, offset=0)
    visible = []
    for task in tasks:
        scope = ProjectService.task_scope(task.task_id, user.user_id)
        if scope or user.role == UserRole.ADMIN:
            visible.append(task)
    return visible[offset:offset + limit]


@router.get("/{task_id}", response_model=TaskResult)
def get_task(task_id: str, user: AuthenticatedUser = Depends(get_current_user)):
    """Get status and details of a single task."""
    return _require_task_owner(task_id, user)


@router.post("/{task_id}/cancel", response_model=dict)
def cancel_task(task_id: str, user: AuthenticatedUser = Depends(get_current_user)):
    """Cancel a running, pending, or waiting task."""
    _require_task_owner(task_id, user)

    success = TaskService.cancel_task(task_id)
    if not success:
        task = TaskService.get_task(task_id)
        raise HTTPException(
            status_code=400,
            detail=f"Task cannot be cancelled from status: {task.status if task else 'unknown'}",
        )
    return {"status": "CANCELLED", "task_id": task_id}


@router.get("/{task_id}/history", response_model=List[TaskEventResponse])
def get_task_history(
    task_id: str,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    user: AuthenticatedUser = Depends(get_current_user),
):
    """Get the chronological append-only event timeline for a task."""
    _require_task_owner(task_id, user)
    return EventService.list_events(task_id, limit=limit, offset=offset)
