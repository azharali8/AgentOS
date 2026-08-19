"""
AgentOS Phase 4 — Coding Service for orchestrating autonomous engineering workflows.
"""

from __future__ import annotations

import logging
import threading
import uuid
from typing import Any, Dict, List, Optional

from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command

try:
    from langgraph.errors import GraphInterrupt
except ImportError:
    GraphInterrupt = Exception  # type: ignore

from backend.app.models.coding import CodingReport
from backend.app.models.task import TaskRequest, TaskResult, TaskStatus
from backend.app.services.event_service import EventService
from backend.app.services.task_service import TaskService
from backend.app.workflows.coding_state import CodingAgentState
from backend.app.workflows.coding_workflow import get_coding_graph

logger = logging.getLogger("agentos.coding_service")

# In-memory registry for active coding states and reports
_active_coding_states: Dict[str, CodingAgentState] = {}


class CodingService:
    """Entry point for starting and resuming autonomous software engineering workflows."""

    @staticmethod
    def start_coding_task(instruction: str, idempotency_key: Optional[str] = None, sync: bool = False) -> TaskResult:
        """Create a coding task and launch the coding StateGraph."""
        task_req = TaskRequest(instruction=instruction)
        task = TaskService.create_task(task_req, idempotency_key=idempotency_key)
        task_id = task.task_id

        if task.status not in (TaskStatus.PENDING, TaskStatus.PLANNING):
            return task

        TaskService.update_task_status(task_id, TaskStatus.PLANNING)

        initial_state: CodingAgentState = {
            "task_id": task_id,
            "user_instruction": instruction,
            "thread_id": task_id,
            "status": "PLANNING",
            "iteration": 0,
            "max_iterations": 5,
            "debug_attempt": 0,
            "max_debug_attempts": 3,
        }

        graph = get_coding_graph()
        config = {"configurable": {"thread_id": task_id}}

        def _run():
            try:
                TaskService.update_task_status(task_id, TaskStatus.EXECUTING)
                result_state = graph.invoke(initial_state, config=config)
                _active_coding_states[task_id] = result_state

                # Check if interrupted waiting for approval
                current_graph_state = graph.get_state(config)
                if current_graph_state.next and any("approval" in n for n in current_graph_state.next):
                    TaskService.update_task_status(task_id, TaskStatus.WAITING_APPROVAL)
                    return

                final_status = result_state.get("final_status", "COMPLETED")
                if final_status == "COMPLETED":
                    TaskService.update_task_status(task_id, TaskStatus.COMPLETED)
                else:
                    TaskService.update_task_status(task_id, TaskStatus.FAILED)
                TaskService.set_final_response(task_id, result_state.get("final_response", ""))
            except GraphInterrupt as exc:
                # LangGraph paused at interrupt() — approval required.
                # Capture state snapshot before interrupt so get_coding_state() works.
                try:
                    snap = graph.get_state(config)
                    if snap and snap.values:
                        _active_coding_states[task_id] = dict(snap.values)
                except Exception:
                    pass
                # Extract approval_id from interrupt payload if available
                try:
                    interrupt_val = exc.args[0] if exc.args else {}
                    if isinstance(interrupt_val, (list, tuple)) and interrupt_val:
                        first = interrupt_val[0]
                        val = getattr(first, "value", {}) if hasattr(first, "value") else {}
                        if isinstance(val, dict) and val.get("approval_id"):
                            state_snap = _active_coding_states.setdefault(task_id, {})
                            if not state_snap.get("approval_id"):
                                state_snap["approval_id"] = val["approval_id"]
                except Exception:
                    pass
                TaskService.update_task_status(task_id, TaskStatus.WAITING_APPROVAL)
                logger.info("Coding task %s paused for approval: %s", task_id, exc)
            except Exception as exc:
                logger.error("Coding task %s encountered error: %s", task_id, exc, exc_info=True)
                TaskService.set_error(task_id, str(exc))

        if sync:
            _run()
            return TaskService.get_task(task_id)

        thread = threading.Thread(target=_run, daemon=True, name=f"coding-{task_id[:8]}")
        thread.start()
        return TaskService.get_task(task_id)

    @staticmethod
    def resume_approval(task_id: str, approved: bool = True) -> TaskResult:
        """Resume an interrupted coding graph waiting for human approval."""
        graph = get_coding_graph()
        config = {"configurable": {"thread_id": task_id}}

        TaskService.update_task_status(task_id, TaskStatus.EXECUTING)
        try:
            result_state = graph.invoke(
                Command(resume={"approved": approved}),
                config=config
            )
            _active_coding_states[task_id] = result_state

            final_status = result_state.get("final_status", "COMPLETED")
            if final_status == "COMPLETED":
                TaskService.update_task_status(task_id, TaskStatus.COMPLETED)
            else:
                TaskService.update_task_status(task_id, TaskStatus.FAILED)
            TaskService.set_final_response(task_id, result_state.get("final_response", ""))
        except Exception as exc:
            logger.error("Error resuming coding approval for task %s: %s", task_id, exc, exc_info=True)
            TaskService.set_error(task_id, str(exc))

        return TaskService.get_task(task_id)

    @staticmethod
    def get_coding_state(task_id: str) -> Optional[CodingAgentState]:
        """Retrieve the in-memory or checkpointed state of a coding task."""
        if task_id in _active_coding_states:
            return _active_coding_states[task_id]
        graph = get_coding_graph()
        config = {"configurable": {"thread_id": task_id}}
        state_snap = graph.get_state(config)
        if state_snap and state_snap.values:
            return state_snap.values
        return None

    @staticmethod
    def get_diagnosis(task_id: str) -> Optional[Dict[str, Any]]:
        state = CodingService.get_coding_state(task_id)
        if state:
            return state.get("diagnosis")
        return None

    @staticmethod
    def get_final_report(task_id: str) -> Optional[Dict[str, Any]]:
        state = CodingService.get_coding_state(task_id)
        if state:
            return {
                "task_id": task_id,
                "user_instruction": state.get("user_instruction", ""),
                "status": state.get("status", "COMPLETED"),
                "diagnosis": state.get("diagnosis", {}),
                "patch_hash": state.get("patch_hash"),
                "iterations": state.get("iteration", 1),
                "final_response": state.get("final_response", ""),
            }
        return None
