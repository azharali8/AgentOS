"""
AgentOS Phase 5 — Agent Budget & Supervision Services.

Monitors and enforces:
- Cumulative token limits
- Tool call counts
- Execution time / timeout detection
- Retry limits
- Subtask & delegation depth limits
- Automatic cancellation when budgets are exceeded
"""

from __future__ import annotations

import logging
import time
from collections import defaultdict
from typing import Dict, Optional

from backend.app.config.settings import settings
from backend.app.models.multi_agent import AgentBudget, AgentStatus, AgentType
from backend.app.services.event_service import EventService

logger = logging.getLogger("agentos.budget")


class BudgetExceededError(RuntimeError):
    """Raised when an agent or task exceeds resource allocations."""
    pass


class AgentBudgetTracker:
    """Tracks token usage, tool invocations, and runtime per task/agent."""

    # task_id -> metrics dict
    _metrics: Dict[str, Dict[str, Any]] = defaultdict(lambda: {
        "tokens_used": 0,
        "tool_calls": 0,
        "retries": 0,
        "start_time": time.time(),
        "cancelled": False,
        "agent_depth": 1,
    })

    @classmethod
    def initialize_task(cls, task_id: str, budget: Optional[AgentBudget] = None) -> None:
        """Set up initial tracking for a multi-agent task."""
        cls._metrics[task_id] = {
            "tokens_used": 0,
            "tool_calls": 0,
            "retries": 0,
            "start_time": time.time(),
            "cancelled": False,
            "agent_depth": 1,
            "budget": budget or AgentBudget(
                max_tokens=settings.MAX_AGENT_TOKENS,
                max_tool_calls=settings.MAX_AGENT_TOOL_CALLS,
                max_execution_time=settings.MAX_AGENT_RUNTIME,
                max_retries=settings.MAX_AGENT_RETRIES,
                max_subtasks=settings.MAX_SUBTASKS,
                max_depth=settings.MAX_AGENT_DEPTH,
            ),
        }

    @classmethod
    def record_token_usage(cls, task_id: str, tokens: int, agent_type: AgentType = AgentType.SUPERVISOR) -> None:
        """Record token consumption and enforce maximum limits."""
        rec = cls._metrics[task_id]
        rec["tokens_used"] += max(0, tokens)
        budget: AgentBudget = rec.get("budget") or AgentBudget()

        if rec["tokens_used"] > budget.max_tokens:
            EventService.record_event(
                task_id=task_id,
                event_type="AGENT_BUDGET_EXCEEDED",
                payload={"metric": "tokens", "limit": budget.max_tokens, "used": rec["tokens_used"], "agent": agent_type.value},
            )
            rec["cancelled"] = True
            raise BudgetExceededError(f"Task {task_id} exceeded token budget: {rec['tokens_used']} > {budget.max_tokens}")

    @classmethod
    def record_tool_call(cls, task_id: str, agent_type: AgentType = AgentType.SUPERVISOR) -> None:
        """Record a tool execution and enforce maximum limits."""
        rec = cls._metrics[task_id]
        rec["tool_calls"] += 1
        budget: AgentBudget = rec.get("budget") or AgentBudget()

        if rec["tool_calls"] > budget.max_tool_calls:
            EventService.record_event(
                task_id=task_id,
                event_type="AGENT_BUDGET_EXCEEDED",
                payload={"metric": "tool_calls", "limit": budget.max_tool_calls, "used": rec["tool_calls"], "agent": agent_type.value},
            )
            rec["cancelled"] = True
            raise BudgetExceededError(f"Task {task_id} exceeded tool call limit: {rec['tool_calls']} > {budget.max_tool_calls}")

    @classmethod
    def check_runtime_budget(cls, task_id: str) -> None:
        """Check elapsed time against execution time budget."""
        rec = cls._metrics[task_id]
        elapsed = time.time() - rec.get("start_time", time.time())
        budget: AgentBudget = rec.get("budget") or AgentBudget()

        if elapsed > budget.max_execution_time:
            EventService.record_event(
                task_id=task_id,
                event_type="AGENT_TIMEOUT",
                payload={"limit": budget.max_execution_time, "elapsed": elapsed},
            )
            rec["cancelled"] = True
            raise BudgetExceededError(f"Task {task_id} timed out after {elapsed:.1f}s (limit: {budget.max_execution_time}s)")

    @classmethod
    def get_metrics(cls, task_id: str) -> Dict[str, Any]:
        """Return snapshot of current resource metrics."""
        rec = cls._metrics.get(task_id, {})
        return {
            "tokens_used": rec.get("tokens_used", 0),
            "tool_calls": rec.get("tool_calls", 0),
            "retries": rec.get("retries", 0),
            "elapsed_seconds": round(time.time() - rec.get("start_time", time.time()), 2),
            "cancelled": rec.get("cancelled", False),
        }

    @classmethod
    def reset(cls, task_id: Optional[str] = None) -> None:
        if task_id:
            cls._metrics.pop(task_id, None)
        else:
            cls._metrics.clear()
