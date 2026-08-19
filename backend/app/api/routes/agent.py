from typing import Optional
from fastapi import APIRouter, Header, HTTPException

from backend.app.models.task import TaskRequest, TaskResult
from backend.app.services.agent_service import AgentService

router = APIRouter()


@router.post("/agent/run", response_model=TaskResult)
def run_agent(
    request: TaskRequest,
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key"),
):
    """
    Start an agent task asynchronously with optional Idempotency-Key header.
    Returns task_id immediately; poll GET /tasks/{task_id} for status.
    """
    try:
        return AgentService.invoke_workflow(request, idempotency_key=idempotency_key)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/agent/run/sync", response_model=TaskResult)
def run_agent_sync(
    request: TaskRequest,
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key"),
):
    """
    Run an agent task synchronously in the calling thread with optional Idempotency-Key.
    Blocks until the task completes or fails. Intended for testing.
    """
    try:
        return AgentService.invoke_workflow_sync(request, idempotency_key=idempotency_key)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
