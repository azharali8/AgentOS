"""
AgentOS Phase 2 — AgentService

Handles background and synchronous workflow execution, idempotency,
and graph resumption.
"""

from __future__ import annotations

import logging
import threading
from typing import Optional

from backend.app.agents.orchestrator import Orchestrator
from backend.app.models.task import TaskRequest, TaskResult, TaskStatus
from backend.app.services.execution_manager import ExecutionManager
from backend.app.services.task_service import TaskService

logger = logging.getLogger(__name__)


class AgentService:

    @staticmethod
    def invoke_workflow(
        request: TaskRequest,
        llm=None,
        idempotency_key: Optional[str] = None,
    ) -> TaskResult:
        """
        Create a task and start the agent graph in a background thread.
        Supports idempotency: if the idempotency_key was already used with the same
        instruction, returns the existing task without starting duplicate execution.
        """
        task = TaskService.create_task(request, idempotency_key=idempotency_key)
        task_id = task.task_id

        # If it was an existing task that is already completed or in progress, return it
        if task.status not in (TaskStatus.PENDING, TaskStatus.PLANNING):
            return task

        TaskService.update_task_status(task_id, TaskStatus.PLANNING)

        def _run():
            try:
                orchestrator = Orchestrator()
                orchestrator.coordinate(task_id, request.instruction, llm=llm)
            except Exception as exc:
                logger.error("Background task %s failed: %s", task_id, exc, exc_info=True)
                TaskService.set_error(task_id, str(exc))
            finally:
                ExecutionManager.clear_task(task_id)

        thread = threading.Thread(target=_run, daemon=True, name=f"agent-{task_id[:8]}")
        thread.start()

        return TaskService.get_task(task_id)

    @staticmethod
    def invoke_workflow_sync(
        request: TaskRequest,
        llm=None,
        idempotency_key: Optional[str] = None,
    ) -> TaskResult:
        """
        Synchronous variant — runs the graph in the calling thread.
        Used for tests and the /agent/run/sync endpoint.
        """
        task = TaskService.create_task(request, idempotency_key=idempotency_key)
        task_id = task.task_id

        if task.status not in (TaskStatus.PENDING, TaskStatus.PLANNING):
            return task

        TaskService.update_task_status(task_id, TaskStatus.PLANNING)

        try:
            orchestrator = Orchestrator()
            orchestrator.coordinate(task_id, request.instruction, llm=llm)
        except Exception as exc:
            logger.error("Sync task %s failed: %s", task_id, exc, exc_info=True)
            TaskService.set_error(task_id, str(exc))
        finally:
            ExecutionManager.clear_task(task_id)

        return TaskService.get_task(task_id)

    @staticmethod
    def resolve_approval(task_id: str, approval_id: str, approved: bool) -> TaskResult:
        """
        Resolve a pending human approval and resume the graph.
        Runs resume in a background thread, returns current task state.
        """
        task = TaskService.get_task(task_id)
        if not task:
            return None  # type: ignore

        def _resume():
            try:
                orchestrator = Orchestrator()
                orchestrator.resume(task_id, approved=approved, approval_id=approval_id)
            except Exception as exc:
                logger.error("Resume task %s failed: %s", task_id, exc, exc_info=True)
                TaskService.set_error(task_id, str(exc))
            finally:
                ExecutionManager.clear_task(task_id)

        thread = threading.Thread(target=_resume, daemon=True, name=f"resume-{task_id[:8]}")
        thread.start()
        # Give the thread a brief moment to start processing
        thread.join(timeout=0.1)

        return TaskService.get_task(task_id)
