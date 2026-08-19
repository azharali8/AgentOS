"""
AgentOS Phase 1 — Orchestrator

Bridges AgentService ↔ LangGraph compiled graph.

coordinate():   start a new graph run (may pause at approval interrupt)
resume():       resume a paused graph after human approval resolution

Both methods update TaskService status and store/retrieve graph thread configs
so the graph can be properly resumed after a GraphInterrupt.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from langgraph.types import Command

from backend.app.models.agent import AgentState
from backend.app.models.task import TaskStatus
from backend.app.services.task_service import TaskService
from backend.app.workflows.task_graph import get_compiled_graph

logger = logging.getLogger(__name__)

# Sentinel value returned by interrupt() — LangGraph wraps it in GraphInterrupt
try:
    from langgraph.errors import GraphInterrupt
except ImportError:
    # Fallback for version differences
    GraphInterrupt = Exception  # type: ignore


class Orchestrator:
    """Drives the LangGraph StateGraph for a single task execution."""

    def coordinate(self, task_id: str, instruction: str, llm=None) -> None:
        """
        Start or restart the agent graph for a task.

        llm: optional override — allows tests to inject a MockLLMProvider
             without touching global settings.
        """
        graph = get_compiled_graph()

        # Thread config uniquely identifies this task's checkpoint stream
        config = {"configurable": {"thread_id": task_id}}
        if llm is not None:
            config["configurable"]["llm"] = llm

        # Store config so we can resume after an interrupt
        TaskService.store_graph_config(task_id, config)
        TaskService.update_task_status(task_id, TaskStatus.PLANNING)

        initial_state: AgentState = {
            "task_id": task_id,
            "user_request": instruction,
            "plan": [],
            "current_step_index": 0,
            "current_tool_request": None,
            "tool_results": [],
            "observations": [],
            "review_verdict": None,
            "review_reasoning": None,
            "retry_count": 0,
            "replan_count": 0,
            "tool_call_count": 0,
            "pending_approval_id": None,
            "task_status": "PENDING",
            "final_response": None,
            "error": None,
            "next_node": None,
        }

        self._run_graph(graph, initial_state, config, task_id)

    def resume(self, task_id: str, approved: bool, approval_id: str) -> None:
        """
        Resume a graph that is paused at an approval interrupt.

        Security: the approval_id is sent back so approval_node can verify
        the resumed request matches the originally approved request exactly.
        """
        graph = get_compiled_graph()
        config = TaskService.get_graph_config(task_id)
        if not config:
            TaskService.set_error(task_id, "No graph config found for resume")
            return

        resume_value = {"approved": approved, "approval_id": approval_id}
        self._run_graph(graph, Command(resume=resume_value), config, task_id)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _run_graph(
        self,
        graph: Any,
        input_: Any,
        config: Dict,
        task_id: str,
    ) -> None:
        """
        Run (or resume) the graph. Handles GraphInterrupt (approval pause)
        and unexpected exceptions.
        """
        try:
            for chunk in graph.stream(input_, config=config, stream_mode="updates"):
                # In LangGraph 1.0.x with stream_mode="updates", each chunk is a dict
                # mapping node_name -> state_update. But during interrupt the stream
                # raises GraphInterrupt before yielding, so we just track approval here.
                if isinstance(chunk, dict):
                    for node_name, update in chunk.items():
                        if isinstance(update, dict) and update.get("pending_approval_id"):
                            TaskService.set_pending_approval(
                                task_id, update["pending_approval_id"]
                            )

        except GraphInterrupt as exc:
            # Graph paused at interrupt() — expected for approvals.
            # TaskService status is already set to WAITING_APPROVAL by security_node
            # via set_pending_approval. If not set yet, set it now from the interrupt value.
            logger.info("Task %s paused for approval: %s", task_id, exc)
            # Try to extract approval_id from the interrupt exception value
            try:
                interrupt_val = exc.args[0] if exc.args else {}
                if isinstance(interrupt_val, (list, tuple)) and interrupt_val:
                    # LangGraph wraps interrupt value as list of Interrupt objects
                    first = interrupt_val[0]
                    val = getattr(first, "value", {}) if hasattr(first, "value") else {}
                    approval_id = val.get("approval_id") if isinstance(val, dict) else None
                    if approval_id:
                        TaskService.set_pending_approval(task_id, approval_id)
            except Exception:
                pass  # approval_id was already set in security_node

        except Exception as exc:
            logger.error("Task %s graph error: %s", task_id, exc, exc_info=True)
            TaskService.set_error(task_id, f"Unexpected graph error: {exc}")

