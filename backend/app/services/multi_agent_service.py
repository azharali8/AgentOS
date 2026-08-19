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
    def start_task(instruction: str, idempotency_key: Optional[str] = None, sync: bool = False) -> TaskResult:
        """Create task and invoke multi-agent StateGraph."""
        task_req = TaskRequest(instruction=instruction)
        task = TaskService.create_task(task_req, idempotency_key=idempotency_key)
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

                final_status = result_state.get("status", "COMPLETED")
                if final_status == "COMPLETED":
                    TaskService.update_task_status(task_id, TaskStatus.COMPLETED)
                else:
                    TaskService.update_task_status(task_id, TaskStatus.FAILED)
                TaskService.set_final_response(task_id, result_state.get("final_response", ""))
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

            final_status = result_state.get("status", "COMPLETED")
            if final_status == "COMPLETED":
                TaskService.update_task_status(task_id, TaskStatus.COMPLETED)
            else:
                TaskService.update_task_status(task_id, TaskStatus.FAILED)
            TaskService.set_final_response(task_id, result_state.get("final_response", ""))
        except Exception as exc:
            logger.error("Error resuming multi-agent task %s: %s", task_id, exc, exc_info=True)
            TaskService.set_error(task_id, str(exc))

        return TaskService.get_task(task_id)

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
