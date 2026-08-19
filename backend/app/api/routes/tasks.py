from typing import List, Optional
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from datetime import datetime

from backend.app.models.task import TaskResult
from backend.app.services.event_service import EventService
from backend.app.services.task_service import TaskService

router = APIRouter()


class TaskEventResponse(BaseModel):
    event_id: str
    task_id: str
    event_type: str
    timestamp: datetime
    step_id: Optional[str] = None
    payload: Optional[dict] = None


@router.get("", response_model=List[TaskResult])
def list_tasks(
    limit: int = Query(20, ge=1, le=100, description="Max number of tasks to return"),
    offset: int = Query(0, ge=0, description="Offset from start"),
):
    """List tasks with pagination."""
    return TaskService.list_tasks(limit=limit, offset=offset)


@router.get("/{task_id}", response_model=TaskResult)
def get_task(task_id: str):
    """Get status and details of a single task."""
    task = TaskService.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@router.post("/{task_id}/cancel", response_model=dict)
def cancel_task(task_id: str):
    """Cancel a running, pending, or waiting task."""
    task = TaskService.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    success = TaskService.cancel_task(task_id)
    if not success:
        raise HTTPException(
            status_code=400,
            detail=f"Task cannot be cancelled from status: {task.status}",
        )
    return {"status": "CANCELLED", "task_id": task_id}


@router.get("/{task_id}/history", response_model=List[TaskEventResponse])
def get_task_history(
    task_id: str,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    """Get the chronological append-only event timeline for a task."""
    task = TaskService.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    events = EventService.list_events(task_id, limit=limit, offset=offset)
    return events
