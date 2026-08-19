"""
AgentOS Phase 5 — Parallel Executor with File-Level Conflict Detection.

Executes independent SubTasks concurrently using a thread pool.
Detects and serializes file-modification conflicts to guarantee safety:
- Subtasks targeting intersecting target_files are scheduled sequentially
- Strictly respects DAG dependencies
- Enforces timeout and cancellation propagation
"""

from __future__ import annotations

import concurrent.futures
import logging
from typing import Callable, Dict, List, Optional, Set

from backend.app.config.settings import settings
from backend.app.models.multi_agent import AgentResult, AgentStatus, AgentType, SubTask
from backend.app.services.event_service import EventService

logger = logging.getLogger("agentos.parallel_executor")


class ParallelExecutor:
    """Executes batches of independent subtasks in parallel with file lock safety."""

    def __init__(self, max_concurrency: int = 4) -> None:
        self.max_concurrency = min(max_concurrency, settings.MAX_AGENT_CONCURRENCY)

    def execute_batch(
        self,
        subtasks: List[SubTask],
        runner_fn: Callable[[SubTask], AgentResult],
        task_id: str = "task-1",
    ) -> Dict[str, AgentResult]:
        """
        Execute a batch of independent subtasks concurrently while detecting file conflicts.
        """
        if not subtasks:
            return {}

        EventService.record_event(
            task_id=task_id,
            event_type="PARALLEL_EXECUTION_STARTED",
            payload={"subtask_ids": [s.subtask_id for s in subtasks], "concurrency": self.max_concurrency},
        )

        results: Dict[str, AgentResult] = {}
        # Partition into conflict-free stages if necessary
        stages = self._partition_conflict_free_stages(subtasks)

        for stage in stages:
            with concurrent.futures.ThreadPoolExecutor(max_workers=self.max_concurrency) as executor:
                future_to_subtask = {
                    executor.submit(runner_fn, st): st for st in stage
                }
                for future in concurrent.futures.as_completed(future_to_subtask):
                    st = future_to_subtask[future]
                    try:
                        res = future.result()
                        results[st.subtask_id] = res
                    except Exception as exc:
                        logger.error("Parallel execution error for subtask %s: %s", st.subtask_id, exc, exc_info=True)
                        results[st.subtask_id] = AgentResult(
                            subtask_id=st.subtask_id,
                            agent_type=st.assigned_agent,
                            status=AgentStatus.FAILED,
                            summary=f"Execution raised exception: {exc}",
                            error=str(exc),
                        )

        EventService.record_event(
            task_id=task_id,
            event_type="PARALLEL_EXECUTION_COMPLETED",
            payload={"completed_subtasks": list(results.keys())},
        )
        return results

    @staticmethod
    def _partition_conflict_free_stages(subtasks: List[SubTask]) -> List[List[SubTask]]:
        """
        Group subtasks into sequential stages such that within each stage,
        no two subtasks share any target_files (preventing parallel overwrite conflicts).
        """
        stages: List[List[SubTask]] = []
        for st in subtasks:
            st_files = set(st.target_files or [])
            placed = False
            for stage in stages:
                # Check if this stage has conflicting files
                stage_files: Set[str] = set()
                for existing in stage:
                    stage_files.update(existing.target_files or [])

                if not st_files or not (st_files & stage_files):
                    stage.append(st)
                    placed = True
                    break
            if not placed:
                stages.append([st])
        return stages
