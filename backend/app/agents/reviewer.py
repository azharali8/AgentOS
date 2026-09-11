"""
AgentOS Phase 1 — Reviewer

Calls the LLM to classify the outcome of a tool execution step.
The raw output is parsed and validated via ReviewerOutput (Pydantic).

Possible verdicts:
  SUCCESS   — step completed correctly; advance to the next step
  RETRYABLE — transient/recoverable error; replan if within limits
  FATAL     — unrecoverable error; terminate the run immediately
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Tuple, Literal

from pydantic import ValidationError

from backend.app.models.agent import Observation, PlanStep, ReviewerOutput

if TYPE_CHECKING:
    from backend.app.llm.base import BaseLLMProvider

logger = logging.getLogger(__name__)


class ReviewDecision(ReviewerOutput):
    verdict: Literal["SUCCESS", "RETRYABLE", "FATAL"]


# Marker used by MockLLMProvider to identify reviewer calls
REVIEWER_PROMPT_MARKER = "REVIEWER_PROMPT"

SYSTEM_PROMPT = """\
You are a step reviewer for AgentOS.

You will be given:
1. The intended step description.
2. The actual execution result (observation).

Classify the result as one of:
  SUCCESS   — the step achieved its goal
  RETRYABLE — a transient or recoverable error occurred
  FATAL     — an unrecoverable error occurred (security denial, invalid tool, etc.)

Rules:
- Return valid JSON only. No markdown.
- "verdict" must be exactly one of: SUCCESS, RETRYABLE, FATAL
- "reasoning" must be a concise explanation.

Return:
{{"verdict": "SUCCESS|RETRYABLE|FATAL", "reasoning": "<explanation>"}}
"""


def _parse_verdict(raw: str) -> Tuple[str, str]:
    """Parse and validate reviewer JSON output. Returns (verdict, reasoning)."""
    try:
        data = json.loads(raw.strip())
    except json.JSONDecodeError as exc:
        raise ValueError(f"Reviewer returned invalid JSON: {exc}") from exc

    try:
        output = ReviewerOutput.model_validate(data)
    except ValidationError as exc:
        raise ValueError(f"Reviewer output schema invalid: {exc}") from exc

    if output.verdict not in ("SUCCESS", "RETRYABLE", "FATAL"):
        raise ValueError(f"Unknown verdict: {output.verdict}")

    return output.verdict, output.reasoning


class ReviewerAgent:
    """LLM-driven step reviewer with Pydantic-validated output."""

    def __init__(self, llm: "BaseLLMProvider", strict: bool = False):
        self.llm = llm
        self.strict = strict

    def review(self, step: PlanStep, observation: Observation) -> Tuple[str, str]:
        """
        Review an observation against the intended step.

        Returns:
            (verdict, reasoning) where verdict is SUCCESS | RETRYABLE | FATAL
        """
        prompt = (
            f"{REVIEWER_PROMPT_MARKER}\n"
            + SYSTEM_PROMPT
            + f"\nStep description: {step.description}"
            + f"\nObservation (success={observation.success}):"
            + f"\n  data: {observation.data}"
            + f"\n  error: {observation.error}"
        )
        if self.strict:
            prompt += ("\nVerify every requirement of the original request against the source evidence and actual tests. "
                       "Passing tests alone do not prove missing functionality exists. If a required feature is absent "
                       "or unsupported by evidence, return RETRYABLE and identify what is missing.")

        try:
            from backend.app.llm.structured import generate_structured
            raw = (generate_structured(self.llm, prompt, ReviewDecision).model_dump_json()
                   if self.strict else self.llm.generate(prompt))
            return _parse_verdict(raw)
        except Exception as exc:
            if self.strict:
                return "RETRYABLE", f"Model review unavailable: {exc}"
            logger.warning("Reviewer generation/parse failed, using deterministic fallback: %s", exc)
            if observation.success:
                return "SUCCESS", "Step succeeded according to execution evidence."
            return "RETRYABLE", f"Step failed: {observation.error or exc}"
