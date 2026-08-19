"""
AgentOS Phase 2 — Recovery Service

Handles system startup recovery of interrupted tasks and checkpoints.
Ensures dangerous side-effecting operations are never blindly executed twice.
"""

from __future__ import annotations

import logging
from typing import Dict, List

from backend.app.db.database import get_db_session
from backend.app.db.models import TaskModel, ExecutionModel
from backend.app.db.repositories.task_repository import TaskRepository
from backend.app.models.task import TaskStatus
from backend.app.services.event_service import EventService
from backend.app.tools.policy import RecoveryStrategy, classify_tool_request

logger = logging.getLogger(__name__)


class RecoveryService:

    @classmethod
    def recover_tasks_on_startup(cls) -> Dict[str, List[str]]:
        """
        Scan for incomplete tasks on system startup and classify/handle them safely:
          - WAITING_APPROVAL: Remains WAITING_APPROVAL (never auto-executed).
          - EXECUTING: Inspect the last running execution. If UNKNOWN_SIDE_EFFECT -> RECOVERY_REQUIRED.
                      If SAFE_TO_RETRY -> leave for safe recovery.
          - PENDING / PLANNING / REVIEWING: Can safely resume or be marked.
          - COMPLETED / FAILED / CANCELLED: Never resumed.
        """
        recovered: List[str] = []
        waiting_approval: List[str] = []
        recovery_required: List[str] = []
        failed_unrecoverable: List[str] = []

        with get_db_session() as session:
            repo = TaskRepository(session)
            incomplete_tasks = repo.get_incomplete_tasks()

            for task in incomplete_tasks:
                task_id = task.task_id
                status = task.status

                if status == TaskStatus.WAITING_APPROVAL.value:
                    logger.info("Task %s is WAITING_APPROVAL, preserving pending state", task_id)
                    waiting_approval.append(task_id)
                    continue

                if status in (TaskStatus.EXECUTING.value, TaskStatus.REVIEWING.value):
                    # Check if there is an in-flight execution
                    last_exec = (
                        session.query(ExecutionModel)
                        .filter(ExecutionModel.task_id == task_id)
                        .order_by(ExecutionModel.started_at.desc())
                        .first()
                    )

                    if last_exec and last_exec.status == "RUNNING":
                        # Classify the tool request
                        policy = classify_tool_request(
                            last_exec.tool_name,
                            last_exec.operation,
                            {},  # Arguments summary / arguments
                        )

                        if policy.recovery_strategy == RecoveryStrategy.UNKNOWN_SIDE_EFFECT:
                            task.status = TaskStatus.RECOVERY_REQUIRED.value
                            task.error = f"Task was interrupted during side-effecting operation {last_exec.tool_name}.{last_exec.operation}. Manual verification required."
                            repo.update(task)
                            EventService.record_event(
                                task_id=task_id,
                                event_type="TASK_RECOVERY_REQUIRED",
                                step_id=last_exec.step_id,
                                payload={"reason": task.error},
                            )
                            recovery_required.append(task_id)
                            continue
                        else:
                            # Safe to retry
                            recovered.append(task_id)
                            continue

                    # If no running execution was recorded or it's safe
                    recovered.append(task_id)
                elif status in (TaskStatus.PENDING.value, TaskStatus.PLANNING.value):
                    recovered.append(task_id)

        return {
            "recovered": recovered,
            "waiting_approval": waiting_approval,
            "recovery_required": recovery_required,
            "failed_unrecoverable": failed_unrecoverable,
        }
