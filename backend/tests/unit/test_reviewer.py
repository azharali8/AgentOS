"""
Tests for the ReviewerAgent — exercises LLM output parsing, Pydantic validation,
verdict classification, and fallback behavior.
"""

import json
import pytest

from backend.app.agents.reviewer import ReviewerAgent
from backend.app.llm.mock import MockLLMProvider
from backend.app.models.agent import Observation, PlanStep


def _step(description: str = "List workspace") -> PlanStep:
    return PlanStep(
        step_id="s1",
        tool_name="filesystem",
        operation="list",
        arguments={"path": "."},
        description=description,
    )


def _obs(success: bool, data=None, error=None) -> Observation:
    return Observation(
        step_id="s1",
        tool_name="filesystem",
        operation="list",
        success=success,
        data=data,
        error=error,
    )


class TestReviewerSuccess:
    def test_success_verdict(self):
        mock = MockLLMProvider(default_review={"verdict": "SUCCESS", "reasoning": "ok"})
        reviewer = ReviewerAgent(mock)
        verdict, reasoning = reviewer.review(_step(), _obs(success=True, data=["file.py"]))
        assert verdict == "SUCCESS"
        assert "ok" in reasoning

    def test_retryable_verdict(self):
        mock = MockLLMProvider()
        mock.push_json({"verdict": "RETRYABLE", "reasoning": "transient error"})
        reviewer = ReviewerAgent(mock)
        verdict, _ = reviewer.review(_step(), _obs(success=False, error="connection reset"))
        assert verdict == "RETRYABLE"

    def test_fatal_verdict(self):
        mock = MockLLMProvider()
        mock.push_json({"verdict": "FATAL", "reasoning": "no such tool"})
        reviewer = ReviewerAgent(mock)
        verdict, _ = reviewer.review(_step(), _obs(success=False, error="tool not found"))
        assert verdict == "FATAL"


class TestReviewerFallback:
    def test_malformed_json_fallback_success(self):
        """If LLM returns bad JSON but observation succeeded, fallback to SUCCESS."""
        mock = MockLLMProvider()
        mock.push("not valid json")
        reviewer = ReviewerAgent(mock)
        verdict, _ = reviewer.review(_step(), _obs(success=True, data="result"))
        assert verdict == "SUCCESS"

    def test_malformed_json_fallback_retryable(self):
        """If LLM returns bad JSON and observation failed, fallback to RETRYABLE."""
        mock = MockLLMProvider()
        mock.push("not valid json")
        reviewer = ReviewerAgent(mock)
        verdict, _ = reviewer.review(_step(), _obs(success=False, error="error"))
        assert verdict == "RETRYABLE"

    def test_invalid_verdict_raises_then_fallback(self):
        """Unknown verdict → fallback to RETRYABLE (observation failed)."""
        mock = MockLLMProvider()
        mock.push_json({"verdict": "MAYBE", "reasoning": "unknown"})
        reviewer = ReviewerAgent(mock)
        verdict, _ = reviewer.review(_step(), _obs(success=False, error="err"))
        assert verdict == "RETRYABLE"
