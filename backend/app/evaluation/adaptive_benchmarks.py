"""
AgentOS Phase 7 - Deterministic Adaptive Benchmarks.

This suite is separate from the Phase 6 benchmark contract so the original
12-case benchmark remains stable while Phase 7 can expose a richer adaptive
evaluation battery.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List

from backend.app.agents.judge import ResultJudgeAgent
from backend.app.intelligence.execution_history import ExecutionHistory
from backend.app.intelligence.failure_analyzer import FailureAnalyzer
from backend.app.intelligence.intelligence_manager import IntelligenceManager
from backend.app.intelligence.model_router import ModelRouter
from backend.app.intelligence.resource_allocator import AdaptiveResourceAllocator
from backend.app.intelligence.strategy import ExecutionStrategy, StrategySelector
from backend.app.llm.mock import MockLLMProvider
from backend.app.memory.manager import AgentMemoryManager
from backend.app.models.coding import FailureInfo
from backend.app.models.experience import FailureCategory
from backend.app.models.multi_agent import AgentType, SubTask
from backend.app.observability.redaction import redact_secrets
from backend.app.security.permissions import SecurityManager
from backend.app.services.parallel_executor import ParallelExecutor
from backend.app.services.task_decomposer import TaskDecomposer
from backend.app.evaluation.benchmark import BenchmarkResult
from backend.app.intelligence.plan_scorer import PlanScorer
from backend.app.intelligence.self_evaluator import SelfEvaluator


class AdaptiveBenchmarkSuite:
    """Deterministic benchmark battery for Phase 7 adaptive intelligence."""

    @classmethod
    def run_all(cls) -> Dict[str, Any]:
        results: List[BenchmarkResult] = []
        for case_fn in cls._cases():
            results.append(cls._run_case(case_fn))

        passed_count = sum(1 for r in results if r.passed)
        total = len(results)
        return {
            "total_cases": total,
            "passed_count": passed_count,
            "failed_count": total - passed_count,
            "success_rate_pct": round((passed_count / max(1, total)) * 100.0, 1),
            "results": [r.model_dump() for r in results],
        }

    @classmethod
    def _run_case(cls, case_fn: Callable[[], BenchmarkResult]) -> BenchmarkResult:
        try:
            return case_fn()
        except Exception as exc:
            return BenchmarkResult(
                case_id=case_fn.__name__,
                name=case_fn.__name__,
                passed=False,
                duration_seconds=0.0,
                error=str(exc),
            )

    @staticmethod
    def _cases() -> List[Callable[[], BenchmarkResult]]:
        return [
            AdaptiveBenchmarkSuite._case_strategy_selection,
            AdaptiveBenchmarkSuite._case_model_routing,
            AdaptiveBenchmarkSuite._case_adaptive_decomposition,
            AdaptiveBenchmarkSuite._case_plan_scoring,
            AdaptiveBenchmarkSuite._case_failure_pattern_detection,
            AdaptiveBenchmarkSuite._case_memory_ranking,
            AdaptiveBenchmarkSuite._case_resource_allocation,
            AdaptiveBenchmarkSuite._case_self_evaluation,
            AdaptiveBenchmarkSuite._case_model_fallback,
            AdaptiveBenchmarkSuite._case_history_knowledge,
            AdaptiveBenchmarkSuite._case_multi_agent_coordination,
            AdaptiveBenchmarkSuite._case_security_preservation,
            AdaptiveBenchmarkSuite._case_secret_redaction,
            AdaptiveBenchmarkSuite._case_infinite_loop_prevention,
            AdaptiveBenchmarkSuite._case_regression_protection,
        ]

    @staticmethod
    def _case_strategy_selection() -> BenchmarkResult:
        strategy = StrategySelector.select_strategy("ab-1", "bug_fix", complexity="medium")
        return BenchmarkResult(case_id="AB-01", name="Strategy Selection", passed=strategy == ExecutionStrategy.DEBUG_THEN_PATCH, duration_seconds=0.0)

    @staticmethod
    def _case_model_routing() -> BenchmarkResult:
        decision = ModelRouter.route("ab-2", "analysis", complexity="complex")
        return BenchmarkResult(case_id="AB-02", name="Model Routing", passed=bool(decision.provider and decision.model), duration_seconds=0.0)

    @staticmethod
    def _case_adaptive_decomposition() -> BenchmarkResult:
        decomposer = TaskDecomposer(llm_provider=MockLLMProvider())
        subtasks = decomposer.adaptive_decompose("Fix failing test in calculator.py", task_id="ab-3", strategy="DEBUG_THEN_PATCH", complexity="complex")
        return BenchmarkResult(case_id="AB-03", name="Adaptive Decomposition", passed=len(subtasks) >= 3, duration_seconds=0.0)

    @staticmethod
    def _case_plan_scoring() -> BenchmarkResult:
        subtasks = [
            SubTask(task_id="ab-4", subtask_id="s1", description="Research", assigned_agent=AgentType.RESEARCH),
            SubTask(task_id="ab-4", subtask_id="s2", description="Fix", assigned_agent=AgentType.CODING, dependencies=["s1"]),
            SubTask(task_id="ab-4", subtask_id="s3", description="Review", assigned_agent=AgentType.REVIEWER, dependencies=["s2"]),
        ]
        score = PlanScorer.score_plan("ab-4", "Fix bug", subtasks, "bug_fix")
        return BenchmarkResult(case_id="AB-04", name="Plan Scoring", passed=score.score > 0.5 and not score.rejected, duration_seconds=0.0)

    @staticmethod
    def _case_failure_pattern_detection() -> BenchmarkResult:
        record = FailureAnalyzer.analyze("assert -1 == 5")
        return BenchmarkResult(case_id="AB-05", name="Failure Pattern Detection", passed=record.pattern == "test_failure", duration_seconds=0.0)

    @staticmethod
    def _case_memory_ranking() -> BenchmarkResult:
        AgentMemoryManager.clear("ab-6")
        AgentMemoryManager.write("ab-6", "project", "overview", "General project notes")
        AgentMemoryManager.write("ab-6", "project", "security", "Avoid exposing tokens and credentials")
        ranked = AgentMemoryManager.retrieve_ranked("ab-6", "project", query="security", limit=2)
        return BenchmarkResult(case_id="AB-06", name="Memory Ranking", passed=bool(ranked) and ranked[0]["key"] == "security", duration_seconds=0.0)

    @staticmethod
    def _case_resource_allocation() -> BenchmarkResult:
        budget = AdaptiveResourceAllocator.allocate_budget("ab-7", complexity="complex", strategy=ExecutionStrategy.ITERATIVE_DEBUG)
        return BenchmarkResult(case_id="AB-07", name="Resource Allocation", passed=AdaptiveResourceAllocator.validate_within_limits(budget) and budget.max_tokens > 0, duration_seconds=0.0)

    @staticmethod
    def _case_self_evaluation() -> BenchmarkResult:
        result = SelfEvaluator.evaluate_task(
            task_id="ab-8",
            instruction="Fix bug",
            subtask_results={"s1": {"status": "completed"}},
            success=True,
        )
        return BenchmarkResult(case_id="AB-08", name="Self Evaluation", passed=result.overall_quality >= 0.9, duration_seconds=0.0)

    @staticmethod
    def _case_model_fallback() -> BenchmarkResult:
        decision = ModelRouter.route("ab-9", "general", provider_availability={"ollama": False, "openai": False, "mock": True}, token_budget=1000)
        return BenchmarkResult(case_id="AB-09", name="Model Fallback", passed=decision.fallback_used and decision.provider == "mock", duration_seconds=0.0)

    @staticmethod
    def _case_history_knowledge() -> BenchmarkResult:
        ExecutionHistory.record_execution(
            task_id="ab-10",
            task_category="bug_fix",
            strategy="DEBUG_THEN_PATCH",
            agents_involved=["research", "coding"],
            success=True,
            duration_seconds=4.0,
            iterations=1,
            tools_used=["code.read", "patch.apply"],
            failure_category=None,
        )
        knowledge = ExecutionHistory.build_knowledge_base("bug_fix")
        return BenchmarkResult(case_id="AB-10", name="History Knowledge", passed=knowledge["sample_size"] >= 1 and "DEBUG_THEN_PATCH" in knowledge["successful_strategies"], duration_seconds=0.0)

    @staticmethod
    def _case_multi_agent_coordination() -> BenchmarkResult:
        analysis = IntelligenceManager.analyze_task("ab-11", "Analyze project and fix failing test in calculator.py")
        return BenchmarkResult(case_id="AB-11", name="Multi-Agent Coordination", passed=len(analysis.subtasks) >= 2 and bool(analysis.strategy), duration_seconds=0.0)

    @staticmethod
    def _case_security_preservation() -> BenchmarkResult:
        blocked = not SecurityManager.is_allowed("code", "read", file_path=".env")
        strategy = StrategySelector.select_strategy("ab-12", "general", risk_level="high", has_security_concerns=True)
        return BenchmarkResult(case_id="AB-12", name="Security Preservation", passed=blocked and strategy == ExecutionStrategy.SECURITY_FIRST, duration_seconds=0.0)

    @staticmethod
    def _case_secret_redaction() -> BenchmarkResult:
        redacted = redact_secrets({"token": "ghp_123456789012345678901234567890123456"})
        return BenchmarkResult(case_id="AB-13", name="Secret Redaction", passed=redacted["token"] == "[REDACTED_SECRET]", duration_seconds=0.0)

    @staticmethod
    def _case_infinite_loop_prevention() -> BenchmarkResult:
        from backend.app.workflows.adaptive_workflow import _route_after_execute

        route = _route_after_execute({"subtasks": [{"subtask_id": "s1"}], "completed_subtask_ids": [], "execution_blocked": True})
        return BenchmarkResult(case_id="AB-14", name="Infinite Loop Prevention", passed=route == "aggregate", duration_seconds=0.0)

    @staticmethod
    def _case_regression_protection() -> BenchmarkResult:
        judge = ResultJudgeAgent()
        verdict = judge.evaluate(
            initial_failures=[FailureInfo(test_name="test_add", message="assert -1 == 5")],
            post_patch_test_data={"exit_code": 0, "passed": True, "counts": {"passed": 1, "failed": 0}},
            initial_test_data={"exit_code": 1, "passed": False, "counts": {"passed": 0, "failed": 1}},
        )
        return BenchmarkResult(case_id="AB-15", name="Regression Protection", passed=verdict.verdict.name in ("SUCCESS", "NEW_FAILURE"), duration_seconds=0.0)


if __name__ == "__main__":
    import json

    print(json.dumps(AdaptiveBenchmarkSuite.run_all(), indent=2, default=str))
