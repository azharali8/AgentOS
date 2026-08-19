"""
AgentOS Phase 2 — ExecutionManager

Manages tool execution lifecycle, cancellation requests, running processes,
and persists execution records into ExecutionRepository.
"""

from __future__ import annotations

import datetime
import logging
import threading
import uuid
from typing import Any, Dict, Optional, Set

from backend.app.config.settings import settings
from backend.app.db.database import get_db_session
from backend.app.db.models import ExecutionModel
from backend.app.db.repositories.execution_repository import ExecutionRepository
from backend.app.models.tool import ToolRequest, ToolResult
from backend.app.security.policies import get_policy
from backend.app.services.event_service import EventService
from backend.app.tools.executor import ToolExecutor
from backend.app.tools.policy import classify_tool_request

logger = logging.getLogger(__name__)


class ExecutionManager:
    _cancelled_tasks: Set[str] = set()
    _active_processes: Dict[str, Any] = {}  # task_id -> subprocess.Popen
    _lock = threading.Lock()

    @classmethod
    def request_cancellation(cls, task_id: str) -> None:
        """Mark a task as cancelled and terminate any running process."""
        with cls._lock:
            cls._cancelled_tasks.add(task_id)
            process = cls._active_processes.get(task_id)
            if process:
                try:
                    logger.info("Terminating process for cancelled task %s", task_id)
                    process.terminate()
                    try:
                        process.wait(timeout=2.0)
                    except Exception:
                        process.kill()
                except Exception as exc:
                    logger.warning("Error terminating process for task %s: %s", task_id, exc)

        EventService.record_event(
            task_id=task_id,
            event_type="TASK_CANCELLED",
            payload={"reason": "User requested cancellation"},
        )

    @classmethod
    def is_cancelled(cls, task_id: str) -> bool:
        with cls._lock:
            return task_id in cls._cancelled_tasks

    @classmethod
    def register_process(cls, task_id: str, process: Any) -> None:
        with cls._lock:
            cls._active_processes[task_id] = process

    @classmethod
    def unregister_process(cls, task_id: str) -> None:
        with cls._lock:
            cls._active_processes.pop(task_id, None)

    @classmethod
    def clear_task(cls, task_id: str) -> None:
        with cls._lock:
            cls._cancelled_tasks.discard(task_id)
            cls._active_processes.pop(task_id, None)

    @classmethod
    def execute_tool(
        cls,
        task_id: str,
        step_id: str,
        request: ToolRequest,
        is_post_approval: bool = False,
        retry_number: int = 0,
    ) -> ToolResult:
        """
        Execute a tool request through the execution lifecycle.
        Records execution start/finish and events to the database.
        """
        if cls.is_cancelled(task_id):
            return ToolResult(
                tool_name=request.tool_name,
                success=False,
                error="Execution cancelled",
            )

        operation = request.arguments.get("operation", "default")
        execution_id = str(uuid.uuid4())
        started_at = datetime.datetime.now(datetime.timezone.utc)
        risk = get_policy(request.tool_name, operation).value

        # Record TOOL_STARTED event
        EventService.record_event(
            task_id=task_id,
            event_type="TOOL_STARTED",
            step_id=step_id,
            payload={"tool_name": request.tool_name, "operation": operation},
        )

        # Create execution record
        with get_db_session() as session:
            repo = ExecutionRepository(session)
            exec_model = ExecutionModel(
                execution_id=execution_id,
                task_id=task_id,
                step_id=step_id,
                tool_name=request.tool_name,
                operation=operation,
                started_at=started_at,
                status="RUNNING",
                risk_level=risk,
                retry_number=retry_number,
            )
            repo.create(exec_model)

        # Execute
        try:
            if is_post_approval:
                result = ToolExecutor.execute_post_approval(request, task_id)
            else:
                result = ToolExecutor.execute(request, task_id)
        except Exception as exc:
            result = ToolResult(
                tool_name=request.tool_name,
                success=False,
                error=str(exc),
            )

        completed_at = datetime.datetime.now(datetime.timezone.utc)
        duration_ms = int((completed_at - started_at).total_seconds() * 1000)

        # Truncate summary for persistence (respect MAX_OUTPUT_SIZE)
        raw_output = str(result.data) if result.data is not None else None
        if raw_output and len(raw_output) > settings.MAX_OUTPUT_SIZE:
            raw_output = raw_output[: settings.MAX_OUTPUT_SIZE] + "..."

        error_msg = result.error
        if error_msg and len(error_msg) > 4000:
            error_msg = error_msg[:4000] + "..."

        exec_status = "SUCCESS" if result.success else "FAILED"

        # Update execution record
        with get_db_session() as session:
            repo = ExecutionRepository(session)
            exec_record = repo.get_by_id(execution_id)
            if exec_record:
                exec_record.completed_at = completed_at
                exec_record.duration_ms = duration_ms
                exec_record.status = exec_status
                exec_record.output_summary = raw_output
                exec_record.error = error_msg
                repo.update(exec_record)

        # Record TOOL_COMPLETED / TOOL_FAILED event
        event_type = "TOOL_COMPLETED" if result.success else "TOOL_FAILED"
        EventService.record_event(
            task_id=task_id,
            event_type=event_type,
            step_id=step_id,
            payload={
                "tool_name": request.tool_name,
                "operation": operation,
                "success": result.success,
                "duration_ms": duration_ms,
                "error": result.error,
            },
        )

        return result
