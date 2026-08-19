from __future__ import annotations
import uuid
import datetime
from typing import Any, Dict, Optional, List

from backend.app.models.task import TaskRequest, TaskResult, TaskStatus
from backend.app.db.database import get_db_session
from backend.app.db.models import TaskModel
from backend.app.db.repositories.task_repository import TaskRepository

class TaskService:
    @classmethod
    def _to_result(cls, task_model: TaskModel) -> TaskResult:
        return TaskResult(
            task_id=task_model.task_id,
            user_request=task_model.user_request,
            status=TaskStatus(task_model.status),
            created_at=task_model.created_at,
            started_at=task_model.started_at,
            completed_at=task_model.completed_at,
            current_step=task_model.current_step,
            total_steps=task_model.total_steps,
            retry_count=task_model.retry_count,
            replan_count=task_model.replan_count,
            final_response=task_model.final_response,
            error=task_model.error,
            thread_id=task_model.thread_id,
            approval_id=None, # Will be set separately if needed, or we can fetch the pending approval
            metadata=task_model.task_metadata,
        )

    @classmethod
    def create_task(cls, request: TaskRequest, idempotency_key: Optional[str] = None) -> TaskResult:
        task_id = str(uuid.uuid4())
        
        # If we need idempotency handling, we'd do it here, but let's implement basic for now.
        with get_db_session() as session:
            repo = TaskRepository(session)
            
            # Idempotency handling using metadata
            if idempotency_key:
                all_tasks = session.query(TaskModel).filter(TaskModel.task_metadata.is_not(None)).all()
                existing = next(
                    (t for t in all_tasks if (t.task_metadata or {}).get("idempotency_key") == idempotency_key),
                    None
                )
                if existing:
                    if existing.user_request != request.instruction:
                        raise ValueError("Idempotency key mismatch with different request")
                    return cls._to_result(existing)

            task_model = TaskModel(
                task_id=task_id,
                user_request=request.instruction,
                status=TaskStatus.PENDING.value,
                thread_id=task_id, # LangGraph thread_id
                task_metadata={"idempotency_key": idempotency_key} if idempotency_key else {}
            )
            created = repo.create(task_model)
            return cls._to_result(created)

    @classmethod
    def get_task(cls, task_id: str) -> Optional[TaskResult]:
        with get_db_session() as session:
            repo = TaskRepository(session)
            task = repo.get_by_id(task_id)
            if not task:
                return None
            result = cls._to_result(task)
            # Find pending approval if WAITING_APPROVAL
            if result.status == TaskStatus.WAITING_APPROVAL:
                from backend.app.db.models import ApprovalModel
                pending_app = session.query(ApprovalModel).filter(
                    ApprovalModel.task_id == task_id,
                    ApprovalModel.status == "PENDING"
                ).first()
                if pending_app:
                    result.approval_id = pending_app.approval_id
            return result

    @classmethod
    def update_task_status(cls, task_id: str, status: TaskStatus) -> None:
        with get_db_session() as session:
            repo = TaskRepository(session)
            task = repo.get_by_id(task_id)
            if task:
                task.status = status.value
                repo.update(task)

    @classmethod
    def set_pending_approval(cls, task_id: str, approval_id: str) -> None:
        with get_db_session() as session:
            repo = TaskRepository(session)
            task = repo.get_by_id(task_id)
            if task:
                task.status = TaskStatus.WAITING_APPROVAL.value
                repo.update(task)

    @classmethod
    def set_final_response(cls, task_id: str, response: str) -> None:
        with get_db_session() as session:
            repo = TaskRepository(session)
            task = repo.get_by_id(task_id)
            if task:
                task.final_response = response
                task.status = TaskStatus.COMPLETED.value
                task.completed_at = datetime.datetime.now(datetime.timezone.utc)
                repo.update(task)

    @classmethod
    def set_error(cls, task_id: str, error: str) -> None:
        with get_db_session() as session:
            repo = TaskRepository(session)
            task = repo.get_by_id(task_id)
            if task:
                task.error = error
                task.status = TaskStatus.FAILED.value
                task.completed_at = datetime.datetime.now(datetime.timezone.utc)
                repo.update(task)

    @classmethod
    def cancel_task(cls, task_id: str) -> bool:
        """Cancel a task. If executing, request termination."""
        with get_db_session() as session:
            repo = TaskRepository(session)
            task = repo.get_by_id(task_id)
            if not task:
                return False
            
            if task.status in [TaskStatus.PENDING.value, TaskStatus.PLANNING.value, TaskStatus.WAITING_APPROVAL.value]:
                task.status = TaskStatus.CANCELLED.value
                task.completed_at = datetime.datetime.now(datetime.timezone.utc)
                repo.update(task)
                return True
            elif task.status in [TaskStatus.EXECUTING.value, TaskStatus.REVIEWING.value]:
                # ExecutionManager handles the actual subprocess cancellation
                from backend.app.services.execution_manager import ExecutionManager
                ExecutionManager.request_cancellation(task_id)
                task.status = TaskStatus.CANCELLED.value
                task.completed_at = datetime.datetime.now(datetime.timezone.utc)
                repo.update(task)
                return True
            return False

    @classmethod
    def list_tasks(cls, limit: int = 20, offset: int = 0) -> List[TaskResult]:
        with get_db_session() as session:
            repo = TaskRepository(session)
            tasks = repo.list_tasks(limit, offset)
            return [cls._to_result(t) for t in tasks]

    _graph_configs: Dict[str, Dict[str, Any]] = {}

    @classmethod
    def get_graph_config(cls, task_id: str) -> Optional[Dict[str, Any]]:
        if task_id in cls._graph_configs:
            return cls._graph_configs[task_id]
        return {"configurable": {"thread_id": task_id}}

    @classmethod
    def store_graph_config(cls, task_id: str, config: Dict[str, Any]) -> None:
        cls._graph_configs[task_id] = config
