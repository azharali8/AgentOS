"""
AgentOS Phase 1 — Planner

Calls the LLM to produce a structured JSON execution plan.
The raw output is parsed and validated via PlannerOutput (Pydantic).

Security properties:
  - MAX_PLAN_STEPS is enforced (server-side config — never from LLM)
  - All tool_name / operation fields are validated against ToolRegistry
  - Malformed JSON triggers up to 2 retries, then raises PlannerError
  - The LLM cannot modify any execution limits
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, List

from pydantic import ValidationError

from backend.app.config.settings import settings
from backend.app.models.agent import AgentState, PlanStep, PlannerOutput

if TYPE_CHECKING:
    from backend.app.llm.base import BaseLLMProvider

logger = logging.getLogger(__name__)


class PlannerError(Exception):
    """Raised when planning fails and cannot be recovered."""


SYSTEM_PROMPT = """\
You are a task execution planner for AgentOS.

Your job is to decompose a user task into a precise, ordered sequence of tool calls.

Available tools and operations:
{tool_catalogue}

Rules:
- Only use tools and operations listed above.
- Each step must reference a real tool_name and operation.
- Return valid JSON — no markdown, no code fences.
- If no tools are needed, return {{"steps": []}}.
- Respect the maximum plan size: {max_steps} steps.

Return exactly this JSON schema:
{{
  "steps": [
    {{
      "step_id": "<unique-string>",
      "tool_name": "<tool_name>",
      "operation": "<operation>",
      "arguments": {{...}},
      "description": "<human-readable description>"
    }}
  ]
}}
"""  # noqa: E501

REPLAN_SYSTEM_PROMPT = """\
You are a task execution replanner for AgentOS.

A previous plan failed. Your job is to generate a revised plan that avoids the same errors.

Original task: {user_request}

Previous errors:
{errors}

Previous observations:
{observations}

Available tools and operations:
{tool_catalogue}

Rules:
- Only use tools and operations listed above.
- Return valid JSON — no markdown, no code fences.
- Respect the maximum plan size: {max_steps} steps.

REPLAN

Return exactly this JSON schema:
{{
  "steps": [
    {{
      "step_id": "<unique-string>",
      "tool_name": "<tool_name>",
      "operation": "<operation>",
      "arguments": {{...}},
      "description": "<human-readable description>"
    }}
  ]
}}
"""

# Marker used by MockLLMProvider to identify planner calls
PLANNER_PROMPT_MARKER = "PLANNER_PROMPT"
REPLAN_MARKER = "REPLAN"


def _build_tool_catalogue() -> str:
    """Enumerate registered tools and their operations from the policies config."""
    from backend.app.security.policies import DEFAULT_POLICIES

    lines: List[str] = []
    for key in DEFAULT_POLICIES:
        tool, op = key.split(".", 1)
        lines.append(f"  - {tool} / {op}")
    return "\n".join(lines) if lines else "  (none registered)"


def _parse_and_validate(raw: str) -> List[PlanStep]:
    """Parse raw LLM JSON string, validate with Pydantic, return PlanStep list."""
    try:
        data = json.loads(raw.strip())
    except json.JSONDecodeError as exc:
        raise PlannerError(f"LLM returned invalid JSON: {exc}") from exc

    try:
        output = PlannerOutput.model_validate(data)
    except ValidationError as exc:
        raise PlannerError(f"Planner output schema invalid: {exc}") from exc

    # Validate against ToolRegistry and policy
    from backend.app.security.policies import DEFAULT_POLICIES
    for step in output.steps:
        key = f"{step.tool_name}.{step.operation}"
        if key not in DEFAULT_POLICIES:
            raise PlannerError(
                f"Step '{step.step_id}' references unknown tool/operation: {key}"
            )

    # Enforce server-side step limit — LLM cannot override this
    if len(output.steps) > settings.MAX_PLAN_STEPS:
        raise PlannerError(
            f"Plan exceeds MAX_PLAN_STEPS ({settings.MAX_PLAN_STEPS}): "
            f"got {len(output.steps)} steps."
        )

    return output.steps


class Planner:
    """LLM-driven planner with Pydantic validation."""

    MAX_PARSE_RETRIES = 2

    def __init__(self, llm: "BaseLLMProvider"):
        self.llm = llm

    def plan(self, state: AgentState) -> List[PlanStep]:
        """
        Generate an initial execution plan from the user request.
        Retries up to MAX_PARSE_RETRIES times on parse failure.
        """
        catalogue = _build_tool_catalogue()
        prompt = (
            f"{PLANNER_PROMPT_MARKER}\n"
            + SYSTEM_PROMPT.format(
                tool_catalogue=catalogue,
                max_steps=settings.MAX_PLAN_STEPS,
            )
            + f"\nUser task: {state['user_request']}"
        )

        return self._call_with_retry(prompt)

    def replan(self, state: AgentState) -> List[PlanStep]:
        """
        Generate a revised plan given the current errors / observations.
        The LLM cannot change execution limits.
        """
        catalogue = _build_tool_catalogue()
        errors_str = "\n".join(state.get("errors", []) or [])
        obs_str = json.dumps(state.get("observations", []), indent=2)

        prompt = (
            f"{PLANNER_PROMPT_MARKER}\n"
            + REPLAN_SYSTEM_PROMPT.format(
                user_request=state["user_request"],
                errors=errors_str or "(none)",
                observations=obs_str,
                tool_catalogue=catalogue,
                max_steps=settings.MAX_PLAN_STEPS,
            )
        )

        return self._call_with_retry(prompt)

    def _call_with_retry(self, prompt: str) -> List[PlanStep]:
        last_error: Exception = PlannerError("No attempts made")
        for attempt in range(self.MAX_PARSE_RETRIES + 1):
            try:
                raw = self.llm.generate(prompt)
                return _parse_and_validate(raw)
            except PlannerError as exc:
                last_error = exc
                logger.warning("Planner parse attempt %d failed: %s", attempt + 1, exc)

        raise PlannerError(
            f"Planner failed after {self.MAX_PARSE_RETRIES + 1} attempts: {last_error}"
        )
