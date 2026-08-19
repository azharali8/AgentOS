"""
AgentOS Phase 7 - Deterministic Adaptive Intelligence Demo.

Walks through the adaptive flow:
classification -> history -> strategy -> model routing -> decomposition ->
plan scoring -> resource allocation -> intentional failure -> failure pattern
detection -> fallback/replan -> successful completion -> self evaluation ->
history recording -> final report.
"""

from __future__ import annotations

from typing import Any, Dict, List

from pydantic import BaseModel, Field

from backend.app.agents.adaptive_supervisor import AdaptiveSupervisorAgent
from backend.app.intelligence.execution_history import ExecutionHistory
from backend.app.intelligence.failure_analyzer import FailureAnalyzer
from backend.app.intelligence.intelligence_manager import IntelligenceManager
from backend.app.intelligence.model_router import ModelRouter
from backend.app.intelligence.self_evaluator import SelfEvaluator
from backend.app.intelligence.strategy import ExecutionStrategy, StrategySelector


class AdaptiveDemoResult(BaseModel):
    task_id: str
    instruction: str
    initial_analysis: Dict[str, Any] = Field(default_factory=dict)
    intentional_failure: Dict[str, Any] = Field(default_factory=dict)
    fallback_routing: Dict[str, Any] = Field(default_factory=dict)
    recovery_analysis: Dict[str, Any] = Field(default_factory=dict)
    history_record_id: str = ""
    evaluation: Dict[str, Any] = Field(default_factory=dict)
    final_report: str = ""
    steps: List[str] = Field(default_factory=list)


class AdaptiveDemo:
    """Deterministic adaptive runtime demonstration."""

    @classmethod
    def run(cls) -> AdaptiveDemoResult:
        task_id = "adaptive-demo-1"
        instruction = "Fix the failing calculator test, recover from the failure, and document the solution."

        initial_analysis = IntelligenceManager.analyze_task(
            task_id=task_id,
            instruction=instruction,
            task_category="bug_fix",
            complexity="complex",
            risk_level="low",
        ).model_dump(mode="json")

        failure_record = FailureAnalyzer.record_failure(
            task_id=task_id,
            message="assert -1 == 5",
            context={"component": "calculator.py", "test": "test_add"},
            resolution="Replace subtraction with addition in add().",
        ).model_dump(mode="json")

        fallback_routing = ModelRouter.route(
            task_id=task_id,
            task_category="bug_fix",
            complexity="complex",
            provider_availability={"ollama": False, "openai": False, "mock": True},
            failure_history={"ollama": 1, "openai": 1, "mock": 0},
        ).model_dump(mode="json")

        recovery_analysis = IntelligenceManager.analyze_task(
            task_id=task_id,
            instruction=instruction,
            task_category="bug_fix",
            complexity="complex",
            risk_level="low",
        ).model_dump(mode="json")

        history_record_id = IntelligenceManager.record_history(
            task_id=task_id,
            task_category="bug_fix",
            strategy=recovery_analysis["strategy"],
            success=True,
            agents_involved=["research", "debugger", "coding", "reviewer", "documentation"],
            duration_seconds=8.5,
            iterations=2,
            tools_used=["code.read", "test.run", "patch.apply"],
        )

        evaluation = SelfEvaluator.evaluate_task(
            task_id=task_id,
            instruction=instruction,
            subtask_results={
                "research": {"status": "completed"},
                "debugger": {"status": "completed"},
                "coding": {"status": "completed"},
                "reviewer": {"status": "completed"},
            },
            success=True,
            iterations=2,
            strategy=recovery_analysis["strategy"],
            agents_used=["research", "debugger", "coding", "reviewer"],
            resource_usage={"tokens_used": 4200, "tool_calls": 6},
        ).model_dump(mode="json")

        supervisor = AdaptiveSupervisorAgent()
        final_report = supervisor.synthesize_response(
            instruction,
            {
                "all_succeeded": True,
                "completed_count": 4,
                "total_subtasks": 4,
                "files_modified": ["calculator.py"],
                "conflicts": [],
            },
            task_id,
        )
        final_report += (
            "\nIntentional Failure: "
            + failure_record["pattern"]
            + " detected and recovered.\n"
            + f"Fallback Routing: {fallback_routing['provider']}/{fallback_routing['model']}\n"
            + f"Quality Score: {evaluation['overall_quality']}\n"
        )

        return AdaptiveDemoResult(
            task_id=task_id,
            instruction=instruction,
            initial_analysis=initial_analysis,
            intentional_failure=failure_record,
            fallback_routing=fallback_routing,
            recovery_analysis=recovery_analysis,
            history_record_id=history_record_id,
            evaluation=evaluation,
            final_report=final_report,
            steps=[
                "classification",
                "historical_analysis",
                "strategy_selection",
                "model_routing",
                "adaptive_decomposition",
                "plan_scoring",
                "resource_allocation",
                "intentional_failure",
                "failure_detection",
                "fallback_replan",
                "successful_completion",
                "self_evaluation",
                "history_recording",
                "final_report",
            ],
        )


if __name__ == "__main__":
    import json

    print(json.dumps(AdaptiveDemo.run().model_dump(mode="json"), indent=2, default=str))
