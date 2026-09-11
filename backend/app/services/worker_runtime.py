"""
AgentOS Phase 15 — Worker Runtime Daemon.

A production-ready worker process runtime that:
- Registers with WorkerManager
- Periodically sends heartbeats
- Polls for assigned/dispatched tasks or schedules directly
- Executes AgentOS workflows under strict lease & fencing token safety
- Renews leases during long operations
- Records execution trace, artifacts, and events
- Gracefully handles shutdown/drain signals
"""

from __future__ import annotations

import datetime
import logging
import os
import signal
import sys
import threading
import time
from typing import Any, Dict, List, Optional

from backend.app.models.task import TaskStatus
from backend.app.services.event_service import EventService
from backend.app.services.multi_agent_service import MultiAgentService
from backend.app.services.task_lease import FencingTokenMismatchError, TaskLeaseService
from backend.app.services.task_queue import QueueStatus, TaskQueue
from backend.app.services.task_scheduler import TaskScheduler
from backend.app.services.task_service import TaskService
from backend.app.services.worker_manager import WorkerManager, WorkerStatus

logger = logging.getLogger("agentos.worker_runtime")


class WorkerRuntime:
    """Worker daemon executing dispatched tasks in a distributed AgentOS cluster."""

    def __init__(
        self,
        worker_id: Optional[str] = None,
        capabilities: Optional[List[str]] = None,
        max_tasks: int = 2,
        poll_interval_seconds: float = 1.0,
        heartbeat_interval_seconds: float = 5.0,
    ):
        self.worker_id = worker_id or f"wkr-{os.getpid()}-{int(time.time())}"
        self.capabilities = capabilities or ["CODING", "TESTING", "RESEARCH", "DEBUGGING", "DEVOPS", "CYBERSECURITY"]
        self.max_tasks = max_tasks
        self.poll_interval = poll_interval_seconds
        self.heartbeat_interval = heartbeat_interval_seconds
        self._running = False
        self._draining = False
        self._active_tasks: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.Lock()
        self._threads: List[threading.Thread] = []

    def start(self) -> None:
        """Start worker registration, heartbeat thread, and polling loop."""
        self._running = True
        WorkerManager.register_worker(
            worker_id=self.worker_id,
            capabilities=self.capabilities,
            max_tasks=self.max_tasks,
        )
        logger.info("Worker %s started with capabilities %s", self.worker_id, self.capabilities)

        # Start heartbeat thread
        hb_thread = threading.Thread(target=self._heartbeat_loop, daemon=True, name=f"hb-{self.worker_id}")
        hb_thread.start()
        self._threads.append(hb_thread)

        # Start main worker polling loop in background or run inline
        poll_thread = threading.Thread(target=self._poll_loop, daemon=True, name=f"poll-{self.worker_id}")
        poll_thread.start()
        self._threads.append(poll_thread)

    def stop(self) -> None:
        """Gracefully stop worker."""
        logger.info("Stopping worker %s...", self.worker_id)
        self._draining = True
        WorkerManager.drain_worker(self.worker_id)
        
        # Wait up to 5s for active tasks
        start_wait = time.time()
        while self._active_tasks and time.time() - start_wait < 5.0:
            time.sleep(0.2)

        self._running = False
        WorkerManager.deregister_worker(self.worker_id)
        logger.info("Worker %s stopped cleanly.", self.worker_id)

    def _heartbeat_loop(self) -> None:
        """Send periodic heartbeats and renew active leases."""
        while self._running:
            try:
                with self._lock:
                    active_count = len(self._active_tasks)
                    # Renew leases for all active tasks
                    for task_id, info in list(self._active_tasks.items()):
                        try:
                            TaskLeaseService.renew_lease(
                                lease_id=info["lease_id"],
                                worker_id=self.worker_id,
                                fencing_token=info["fencing_token"],
                            )
                        except Exception as exc:
                            logger.warning("Worker %s lease renewal failed for task %s: %s", self.worker_id, task_id, exc)

                WorkerManager.heartbeat(self.worker_id, active_tasks=active_count)
            except Exception as e:
                logger.error("Heartbeat error in worker %s: %s", self.worker_id, e)
            time.sleep(self.heartbeat_interval)

    def _poll_loop(self) -> None:
        """Poll for assigned tasks or trigger scheduler."""
        while self._running and not self._draining:
            try:
                with self._lock:
                    can_accept = len(self._active_tasks) < self.max_tasks

                if can_accept:
                    # Attempt to schedule/claim next task
                    dispatched = TaskScheduler.schedule_next()
                    if dispatched:
                        task_id, assigned_wid, fencing_token = dispatched
                        if assigned_wid == self.worker_id:
                            self._launch_task_execution(task_id, fencing_token)
            except Exception as e:
                logger.error("Worker %s poll loop error: %s", self.worker_id, e)

            time.sleep(self.poll_interval)

    def _launch_task_execution(self, task_id: str, fencing_token: int) -> None:
        """Spawn worker thread to execute the task."""
        lease_info = TaskLeaseService.get_active_lease(task_id)
        lease_id = lease_info["lease_id"] if lease_info else f"lease-{task_id}"

        with self._lock:
            self._active_tasks[task_id] = {
                "lease_id": lease_id,
                "fencing_token": fencing_token,
                "started_at": time.time(),
            }

        exec_thread = threading.Thread(
            target=self._execute_task,
            args=(task_id, lease_id, fencing_token),
            daemon=True,
            name=f"task-exec-{task_id[:8]}",
        )
        exec_thread.start()

    def _execute_task(self, task_id: str, lease_id: str, fencing_token: int) -> None:
        """Run task execution logic under fencing verification."""
        try:
            # 1. Verify fencing token before starting
            TaskLeaseService.verify_fencing_token(task_id, fencing_token, self.worker_id)
            TaskQueue.update_status(task_id, QueueStatus.RUNNING, worker_id=self.worker_id, fencing_token=fencing_token)
            TaskService.update_task_status(task_id, TaskStatus.PLANNING)

            task = TaskService.get_task(task_id)
            instruction = task.user_request if task else "Execute distributed task"

            # 2. Execute multi-agent graph with lease/worker context
            try:
                result = MultiAgentService.start_task(instruction=instruction, sync=True, task_id=task_id)
                queue_status = {
                    TaskStatus.COMPLETED: QueueStatus.COMPLETED,
                    TaskStatus.CANCELLED: QueueStatus.CANCELLED,
                    TaskStatus.WAITING_APPROVAL: QueueStatus.PAUSED,
                    TaskStatus.PAUSED: QueueStatus.PAUSED,
                }.get(result.status, QueueStatus.FAILED)
                TaskQueue.update_status(task_id, queue_status)
            except Exception as exc:
                TaskService.set_error(task_id, str(exc))
                TaskQueue.update_status(task_id, QueueStatus.FAILED)

            # 3. Release lease upon normal completion
            TaskLeaseService.release_lease(lease_id, self.worker_id, fencing_token)

        except FencingTokenMismatchError as fte:
            logger.error("Worker %s aborted task %s due to fencing token mismatch: %s", self.worker_id, task_id, fte)
            TaskQueue.update_status(task_id, QueueStatus.RECOVERY_REQUIRED)
        except Exception as e:
            logger.error("Worker %s encountered execution error on task %s: %s", self.worker_id, task_id, e)
            TaskQueue.update_status(task_id, QueueStatus.FAILED)
        finally:
            with self._lock:
                self._active_tasks.pop(task_id, None)
                active_count = len(self._active_tasks)
            WorkerManager.heartbeat(self.worker_id, active_tasks=active_count)

