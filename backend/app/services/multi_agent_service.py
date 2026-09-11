"""
AgentOS Phase 5 — Multi-Agent Service.

High-level application coordinator for initiating, tracking, and resuming multi-agent tasks.
"""

from __future__ import annotations

import logging
import threading
from typing import Any, Dict, Optional

from langgraph.types import Command

try:
    from langgraph.errors import GraphInterrupt
except ImportError:
    GraphInterrupt = Exception  # type: ignore

from backend.app.models.task import TaskRequest, TaskResult, TaskStatus
from backend.app.services.task_service import TaskService
from backend.app.workflows.multi_agent_state import MultiAgentState
from backend.app.workflows.multi_agent_workflow import get_multi_agent_graph

logger = logging.getLogger("agentos.multi_agent_service")

_active_multi_agent_states: Dict[str, MultiAgentState] = {}


class MultiAgentService:
    """Entry point for multi-agent task execution and resumption."""

    @staticmethod
    def start_task(instruction: str, idempotency_key: Optional[str] = None, sync: bool = False, task_id: Optional[str] = None) -> TaskResult:
        """Create task and invoke multi-agent StateGraph."""
        task_req = TaskRequest(instruction=instruction)
        task = TaskService.get_task(task_id) if task_id else TaskService.create_task(task_req, idempotency_key=idempotency_key)
        if task is None or task.user_request != instruction:
            raise ValueError("Execution must reference the existing task's instruction")
        task_id = task.task_id

        if task.status not in (TaskStatus.PENDING, TaskStatus.PLANNING):
            return task

        TaskService.update_task_status(task_id, TaskStatus.PLANNING)

        initial_state: MultiAgentState = {
            "task_id": task_id,
            "user_instruction": instruction,
            "thread_id": task_id,
            "status": "PLANNING",
            "iteration": 0,
            "subtasks": [],
            "completed_subtask_ids": [],
            "subtask_results": {},
        }

        graph = get_multi_agent_graph()
        config = {"configurable": {"thread_id": task_id}}

        def _run():
            try:
                TaskService.update_task_status(task_id, TaskStatus.EXECUTING)
                result_state = graph.invoke(initial_state, config=config)
                _active_multi_agent_states[task_id] = result_state

                MultiAgentService._persist_outcome(task_id, result_state, graph, config)
            except GraphInterrupt as exc:
                try:
                    snap = graph.get_state(config)
                    if snap and snap.values:
                        _active_multi_agent_states[task_id] = dict(snap.values)
                except Exception:
                    pass
                TaskService.update_task_status(task_id, TaskStatus.WAITING_APPROVAL)
                logger.info("Multi-agent task %s paused for approval: %s", task_id, exc)
            except Exception as exc:
                logger.error("Multi-agent task %s error: %s", task_id, exc, exc_info=True)
                TaskService.set_error(task_id, str(exc))

        if sync:
            _run()
            return TaskService.get_task(task_id)

        thread = threading.Thread(target=_run, daemon=True, name=f"multi-agent-{task_id[:8]}")
        thread.start()
        return TaskService.get_task(task_id)

    @staticmethod
    def resume_approval(task_id: str, approved: bool = True) -> TaskResult:
        """Resume an interrupted multi-agent graph waiting for human approval."""
        graph = get_multi_agent_graph()
        config = {"configurable": {"thread_id": task_id}}

        TaskService.update_task_status(task_id, TaskStatus.EXECUTING)
        try:
            result_state = graph.invoke(
                Command(resume={"approved": approved}),
                config=config,
            )
            _active_multi_agent_states[task_id] = result_state

            MultiAgentService._persist_outcome(task_id, result_state, graph, config)
        except Exception as exc:
            logger.error("Error resuming multi-agent task %s: %s", task_id, exc, exc_info=True)
            TaskService.set_error(task_id, str(exc))

        return TaskService.get_task(task_id)

    @staticmethod
    def _persist_outcome(task_id, state, graph, config):
        current = TaskService.get_task(task_id)
        if current and current.status == TaskStatus.CANCELLED:
            return
        snapshot = graph.get_state(config)
        if state.get("__interrupt__") or (snapshot and any("approval" in n for n in snapshot.next)):
            TaskService.update_task_status(task_id, TaskStatus.WAITING_APPROVAL)
            return
        status = state.get("status", "FAILED")
        if status == "COMPLETED":
            TaskService.set_final_response(task_id, state.get("final_response", ""))
        elif status in ("CANCELLED", "PAUSED", "WAITING_APPROVAL"):
            TaskService.update_task_status(task_id, TaskStatus(status))
        else:
            TaskService.set_error(task_id, state.get("error") or state.get("final_response") or "Supervisor execution failed")

    @staticmethod
    def get_state(task_id: str) -> Optional[MultiAgentState]:
        """Get live or checkpointed multi-agent state."""
        if task_id in _active_multi_agent_states:
            return _active_multi_agent_states[task_id]
        graph = get_multi_agent_graph()
        config = {"configurable": {"thread_id": task_id}}
        snap = graph.get_state(config)
        if snap and snap.values:
            return snap.values
        return None

    @staticmethod
    def get_report(task_id: str) -> Optional[Dict[str, Any]]:
        state = MultiAgentService.get_state(task_id)
        if state:
            return {
                "task_id": task_id,
                "user_instruction": state.get("user_instruction", ""),
                "status": state.get("status", "COMPLETED"),
                "subtasks_count": len(state.get("subtasks", [])),
                "completed_count": len(state.get("completed_subtask_ids", [])),
                "aggregated_results": state.get("aggregated_results", {}),
                "final_response": state.get("final_response", ""),
            }
        return None
