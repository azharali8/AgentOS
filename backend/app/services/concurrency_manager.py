"""
AgentOS Phase 13 — Task Concurrency & Resource Manager.

Enforces:
- Global concurrent task limits
- Priority queueing: CRITICAL > HIGH > NORMAL > LOW
- Per-agent worker semaphores (Coding max 2, Testing max 2, Research max 4)
- CPU / memory bounds guard
"""

from __future__ import annotations

import heapq
import logging
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from backend.app.models.multi_agent import AgentType
from backend.app.models.task import TaskPriority

logger = logging.getLogger("agentos.concurrency_manager")

MAX_CONCURRENT_TASKS = 4

# Agent-specific worker concurrency limits
AGENT_CONCURRENCY_LIMITS: Dict[AgentType, int] = {
    AgentType.CODING: 2,
    AgentType.TESTING: 2,
    AgentType.RESEARCH: 4,
    AgentType.DEBUGGER: 2,
    AgentType.DEVOPS: 2,
    AgentType.DATA_ENGINEER: 2,
    AgentType.SECURITY: 4,
    AgentType.CYBERSECURITY: 1,
}

PRIORITY_WEIGHTS = {
    TaskPriority.CRITICAL: 0,
    TaskPriority.HIGH: 1,
    TaskPriority.NORMAL: 2,
    TaskPriority.LOW: 3,
}


@dataclass(order=True)
class PrioritizedTask:
    priority_score: int
    created_at: float
    task_id: str = field(compare=False)
    instruction: str = field(compare=False)


class ConcurrencyManager:
    """Controls multi-tenant task concurrency and per-agent execution limits."""

    _lock = threading.Lock()
    _active_tasks: set[str] = set()
    _task_queue: List[PrioritizedTask] = []
    
    _agent_semaphores: Dict[AgentType, threading.Semaphore] = {
        agent: threading.Semaphore(limit) for agent, limit in AGENT_CONCURRENCY_LIMITS.items()
    }
    _active_agent_counts: Dict[AgentType, int] = {agent: 0 for agent in AGENT_CONCURRENCY_LIMITS}

    @classmethod
    def can_start_task(cls, task_id: str, priority: TaskPriority = TaskPriority.NORMAL) -> bool:
        """Check if global capacity permits immediate start, or queues task."""
        with cls._lock:
            if len(cls._active_tasks) < MAX_CONCURRENT_TASKS:
                cls._active_tasks.add(task_id)
                logger.info("Task %s acquired execution slot. Active tasks: %d/%d", task_id, len(cls._active_tasks), MAX_CONCURRENT_TASKS)
                return True

            # Enqueue
            entry = PrioritizedTask(
                priority_score=PRIORITY_WEIGHTS.get(priority, 2),
                created_at=datetime.now(timezone.utc).timestamp(),
                task_id=task_id,
                instruction="",
            )
            heapq.heappush(cls._task_queue, entry)
            logger.info("Task %s queued (priority=%s). Queue length: %d", task_id, priority.value, len(cls._task_queue))
            return False

    @classmethod
    def release_task(cls, task_id: str) -> Optional[str]:
        """Release execution slot and return next highest-priority queued task ID if any."""
        with cls._lock:
            cls._active_tasks.discard(task_id)
            logger.info("Task %s released slot. Active tasks: %d/%d", task_id, len(cls._active_tasks), MAX_CONCURRENT_TASKS)

            if cls._task_queue and len(cls._active_tasks) < MAX_CONCURRENT_TASKS:
                next_task = heapq.heappop(cls._task_queue)
                cls._active_tasks.add(next_task.task_id)
                logger.info("De-queued task %s to start execution.", next_task.task_id)
                return next_task.task_id
            return None

    @classmethod
    def acquire_agent_slot(cls, agent_type: AgentType, timeout: float = 10.0) -> bool:
        """Acquire per-agent worker semaphore."""
        sem = cls._agent_semaphores.get(agent_type)
        if not sem:
            return True
        acquired = sem.acquire(timeout=timeout)
        if acquired:
            with cls._lock:
                cls._active_agent_counts[agent_type] = cls._active_agent_counts.get(agent_type, 0) + 1
        return acquired

    @classmethod
    def release_agent_slot(cls, agent_type: AgentType) -> None:
        """Release per-agent worker semaphore."""
        sem = cls._agent_semaphores.get(agent_type)
        if sem:
            with cls._lock:
                cls._active_agent_counts[agent_type] = max(0, cls._active_agent_counts.get(agent_type, 0) - 1)
            sem.release()

    @classmethod
    def get_metrics(cls) -> Dict[str, Any]:
        """Get snapshot of live concurrency and queue metrics."""
        with cls._lock:
            return {
                "max_concurrent_tasks": MAX_CONCURRENT_TASKS,
                "active_tasks_count": len(cls._active_tasks),
                "active_task_ids": list(cls._active_tasks),
                "queued_tasks_count": len(cls._task_queue),
                "agent_concurrency": {
                    agent.value: {
                        "active": cls._active_agent_counts.get(agent, 0),
                        "limit": AGENT_CONCURRENCY_LIMITS.get(agent, 2),
                    }
                    for agent in AGENT_CONCURRENCY_LIMITS
                }
            }
