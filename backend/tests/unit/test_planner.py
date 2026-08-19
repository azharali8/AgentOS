"""
Tests for the Planner — exercises LLM output parsing, Pydantic validation,
ToolRegistry validation, and plan limit enforcement.
"""

import json
import pytest

from backend.app.agents.planner import Planner, PlannerError
from backend.app.llm.mock import MockLLMProvider
from backend.app.models.agent import AgentState


def _make_state(instruction: str = "Test task") -> AgentState:
    return AgentState(
        task_id="test-task-1",
        user_request=instruction,
        plan=[],
        current_step_index=0,
        current_tool_request=None,
        tool_results=[],
        observations=[],
        review_verdict=None,
        review_reasoning=None,
        retry_count=0,
        replan_count=0,
        tool_call_count=0,
        pending_approval_id=None,
        task_status="PENDING",
        final_response=None,
        error=None,
        next_node=None,
    )


def _valid_plan(step_id: str = "s1") -> dict:
    return {
        "steps": [
            {
                "step_id": step_id,
                "tool_name": "filesystem",
                "operation": "list",
                "arguments": {"path": "."},
                "description": "List workspace files",
            }
        ]
    }


class TestPlannerParsingSuccess:
    def test_valid_plan_parses(self):
        mock = MockLLMProvider()
        mock.push_json(_valid_plan())
        planner = Planner(mock)
        steps = planner.plan(_make_state())
        assert len(steps) == 1
        assert steps[0].tool_name == "filesystem"
        assert steps[0].operation == "list"
        assert steps[0].step_id == "s1"

    def test_empty_plan_allowed(self):
        mock = MockLLMProvider()
        mock.push_json({"steps": []})
        planner = Planner(mock)
        steps = planner.plan(_make_state())
        assert steps == []

    def test_multiple_steps_parse(self):
        mock = MockLLMProvider()
        mock.push_json({
            "steps": [
                {"step_id": "s1", "tool_name": "filesystem", "operation": "list",
                 "arguments": {"path": "."}, "description": "list"},
                {"step_id": "s2", "tool_name": "filesystem", "operation": "read",
                 "arguments": {"path": "test.py"}, "description": "read file"},
            ]
        })
        planner = Planner(mock)
        steps = planner.plan(_make_state())
        assert len(steps) == 2


class TestPlannerValidationRejection:
    def test_malformed_json_raises(self):
        mock = MockLLMProvider()
        mock.push("not valid json {{")
        mock.push("still bad")
        mock.push("still bad 2")
        planner = Planner(mock)
        with pytest.raises(PlannerError, match="invalid JSON"):
            planner.plan(_make_state())

    def test_unknown_tool_raises(self):
        mock = MockLLMProvider()
        bad_plan = {
            "steps": [
                {"step_id": "s1", "tool_name": "browser", "operation": "navigate",
                 "arguments": {}, "description": "browse"}
            ]
        }
        mock.push_json(bad_plan)
        mock.push_json(bad_plan)
        mock.push_json(bad_plan)
        planner = Planner(mock)
        with pytest.raises(PlannerError, match="unknown tool/operation"):
            planner.plan(_make_state())

    def test_missing_required_field_raises(self):
        mock = MockLLMProvider()
        bad = {"steps": [{"step_id": "s1", "tool_name": "filesystem"}]}  # missing operation
        mock.push_json(bad)
        mock.push_json(bad)
        mock.push_json(bad)
        planner = Planner(mock)
        with pytest.raises(PlannerError, match="schema invalid"):
            planner.plan(_make_state())

    def test_plan_too_large_raises(self):
        from backend.app.config.settings import settings
        mock = MockLLMProvider()
        big_plan = {
            "steps": [
                {"step_id": f"s{i}", "tool_name": "filesystem", "operation": "list",
                 "arguments": {"path": "."}, "description": f"step {i}"}
                for i in range(settings.MAX_PLAN_STEPS + 1)
            ]
        }
        mock.push_json(big_plan)
        mock.push_json(big_plan)
        mock.push_json(big_plan)
        planner = Planner(mock)
        with pytest.raises(PlannerError, match="MAX_PLAN_STEPS"):
            planner.plan(_make_state())


class TestPlannerReplan:
    def test_replan_produces_new_steps(self):
        replan_response = {
            "steps": [
                {
                    "step_id": "r1",
                    "tool_name": "filesystem",
                    "operation": "list",
                    "arguments": {"path": "."},
                    "description": "Replanned step",
                }
            ]
        }
        mock = MockLLMProvider(default_replan=replan_response)
        planner = Planner(mock)
        state = _make_state()
        state["observations"] = []
        steps = planner.replan(state)
        assert len(steps) == 1
        assert steps[0].step_id == "r1"
        assert steps[0].description == "Replanned step"
