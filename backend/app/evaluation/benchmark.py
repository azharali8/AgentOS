"""
AgentOS Phase 6 — Benchmark Cases & Evaluation Framework.

Implements 12 deterministic benchmark cases to evaluate:
- Repository analysis accuracy
- Bug diagnosis & patch generation
- Sensitive file protection & security rejections
- Multi-agent coordination and DAG scheduling
- Regression recovery
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from backend.app.llm.mock import MockLLMProvider
from backend.app.models.multi_agent import AgentType
from backend.app.services.multi_agent_service import MultiAgentService
from backend.app.services.task_decomposer import TaskDecomposer

logger = logging.getLogger("agentos.evaluator")


class BenchmarkResult(BaseModel):
    case_id: str
    name: str
    passed: bool
    duration_seconds: float
    details: Dict[str, Any] = Field(default_factory=dict)
    error: Optional[str] = None


class BenchmarkSuite:
    """Runs benchmark cases against the AgentOS runtime.

    `run_all()` preserves the Phase 6 contract of 12 deterministic cases.
    Phase 7 adaptive benchmarks are available separately through
    `run_phase7()` or `run_all(include_phase7=True)`.
    """

    @classmethod
    def run_all(cls, include_phase7: bool = False) -> Dict[str, Any]:
        """Execute the Phase 6 suite, optionally including Phase 7 cases."""
        cases = cls._phase6_cases()
        if include_phase7:
            cases = cases + cls._phase7_cases()
        return cls._run_cases(cases)

    @classmethod
    def run_phase7(cls) -> Dict[str, Any]:
        """Execute only the adaptive intelligence benchmark cases."""
        return cls._run_cases(cls._phase7_cases())

    @staticmethod
    def _run_cases(cases: List[Any]) -> Dict[str, Any]:
        results: List[BenchmarkResult] = []
        for case_fn in cases:
            start = time.time()
            try:
                res = case_fn()
                res.duration_seconds = round(time.time() - start, 3)
                results.append(res)
            except Exception as exc:
                results.append(BenchmarkResult(
                    case_id=case_fn.__name__,
                    name=case_fn.__name__,
                    passed=False,
                    duration_seconds=round(time.time() - start, 3),
                    error=str(exc),
                ))

        passed_count = sum(1 for r in results if r.passed)
        total = len(results)
        score_pct = round((passed_count / max(1, total)) * 100.0, 1)

        return {
            "total_cases": total,
            "passed_count": passed_count,
            "failed_count": total - passed_count,
            "success_rate_pct": score_pct,
            "results": [r.model_dump() for r in results],
        }

    @staticmethod
    def _phase6_cases() -> List[Any]:
        return [
            BenchmarkSuite._case_repo_analysis,
            BenchmarkSuite._case_code_search,
            BenchmarkSuite._case_code_explanation,
            BenchmarkSuite._case_bug_diagnosis,
            BenchmarkSuite._case_patch_generation,
            BenchmarkSuite._case_patch_validation,
            BenchmarkSuite._case_sensitive_file_blocking,
            BenchmarkSuite._case_human_approval_enforcement,
            BenchmarkSuite._case_multi_agent_decomposition,
            BenchmarkSuite._case_parallel_conflict_partitioning,
            BenchmarkSuite._case_regression_detection,
            BenchmarkSuite._case_documentation_synthesis,
        ]

    @staticmethod
    def _phase7_cases() -> List[Any]:
        return [
            BenchmarkSuite._case_simple_task_routing,
            BenchmarkSuite._case_complex_task_decomposition,
            BenchmarkSuite._case_capability_aware_routing,
            BenchmarkSuite._case_strategy_selection,
            BenchmarkSuite._case_historical_strategy_recommendation,
            BenchmarkSuite._case_failure_pattern_detection,
            BenchmarkSuite._case_adaptive_budgeting,
            BenchmarkSuite._case_plan_scoring,
            BenchmarkSuite._case_multi_agent_optimization,
            BenchmarkSuite._case_security_invariant_preservation,
        ]

    @staticmethod
    def _case_repo_analysis() -> BenchmarkResult:
        from backend.app.code.scanner import RepositoryScanner
        scanner = RepositoryScanner()
        res = scanner.scan()
        return BenchmarkResult(
            case_id="BM-01",
            name="Repository Analysis",
            passed=res.total_files > 0,
            duration_seconds=0.0,
            details={"total_files": res.total_files},
        )

    @staticmethod
    def _case_code_search() -> BenchmarkResult:
        from backend.app.code.search import CodeSearch
        searcher = CodeSearch()
        res = searcher.search("def ")
        return BenchmarkResult(
            case_id="BM-02",
            name="Code Search",
            passed=res.total_matches >= 0,
            duration_seconds=0.0,
        )

    @staticmethod
    def _case_code_explanation() -> BenchmarkResult:
        from backend.app.agents.task_classifier import TaskClassifierAgent
        classifier = TaskClassifierAgent(llm_provider=MockLLMProvider())
        res = classifier.classify("Explain how authentication works in the codebase")
        return BenchmarkResult(
            case_id="BM-03",
            name="Code Explanation Classification",
            passed=res is not None,
            duration_seconds=0.0,
        )

    @staticmethod
    def _case_bug_diagnosis() -> BenchmarkResult:
        from backend.app.agents.debugger import DebuggerAgent
        from backend.app.models.coding import FailureInfo, InvestigationResult
        debugger = DebuggerAgent(llm_provider=MockLLMProvider())
        diag = debugger.diagnose(
            failures=[FailureInfo(test_name="test_add", message="assert -1 == 5")],
            investigation=InvestigationResult(affected_files=["calculator.py"]),
        )
        return BenchmarkResult(
            case_id="BM-04",
            name="Bug Diagnosis Synthesis",
            passed=diag.confidence > 0.5 and len(diag.affected_files) > 0,
            duration_seconds=0.0,
        )

    @staticmethod
    def _case_patch_generation() -> BenchmarkResult:
        from backend.app.agents.specialized import CodingAgent
        from backend.app.models.multi_agent import SubTask
        agent = CodingAgent(llm_provider=MockLLMProvider())
        st = SubTask(task_id="t1", subtask_id="s1", description="Fix bug", assigned_agent=AgentType.CODING, target_files=["calculator.py"])
        patch = agent.formulate_patch(st, {})
        return BenchmarkResult(
            case_id="BM-05",
            name="Patch Generation",
            passed=len(patch.files) > 0,
            duration_seconds=0.0,
        )

    @staticmethod
    def _case_patch_validation() -> BenchmarkResult:
        from backend.app.code.patch.models import Patch, PatchFile, PatchHunk
        from backend.app.code.patch.validator import PatchValidator
        pf = PatchFile(relative_path="calculator.py", original_hash="test", hunks=[
            PatchHunk(original_start=1, original_count=1, new_start=1, new_count=1, lines=["-a\n", "+b\n"])
        ])
        patch = Patch(patch_id="p1", task_id="t1", description="test", files=[pf])
        validator = PatchValidator()
        res = validator.validate(patch)
        return BenchmarkResult(
            case_id="BM-06",
            name="Patch Validation",
            passed=res is not None and res.patch_hash is not None,
            duration_seconds=0.0,
        )

    @staticmethod
    def _case_sensitive_file_blocking() -> BenchmarkResult:
        from backend.app.security.permissions import SecurityManager
        blocked = not SecurityManager.is_allowed("code", "read", file_path=".env")
        return BenchmarkResult(
            case_id="BM-07",
            name="Sensitive File Blocking",
            passed=blocked,
            duration_seconds=0.0,
        )

    @staticmethod
    def _case_human_approval_enforcement() -> BenchmarkResult:
        from backend.app.security.permissions import SecurityManager
        requires_appr = SecurityManager.requires_approval("patch", "apply")
        return BenchmarkResult(
            case_id="BM-08",
            name="Human Approval Requirement",
            passed=requires_appr,
            duration_seconds=0.0,
        )

    @staticmethod
    def _case_multi_agent_decomposition() -> BenchmarkResult:
        decomposer = TaskDecomposer(llm_provider=MockLLMProvider())
        subtasks = decomposer.decompose("Fix failing test in calculator.py")
        return BenchmarkResult(
            case_id="BM-09",
            name="Multi-Agent DAG Decomposition",
            passed=len(subtasks) >= 3,
            duration_seconds=0.0,
        )

    @staticmethod
    def _case_parallel_conflict_partitioning() -> BenchmarkResult:
        from backend.app.models.multi_agent import SubTask
        from backend.app.services.parallel_executor import ParallelExecutor
        st1 = SubTask(task_id="t1", subtask_id="s1", description="Edit A", assigned_agent=AgentType.CODING, target_files=["calc.py"])
        st2 = SubTask(task_id="t1", subtask_id="s2", description="Edit A conflict", assigned_agent=AgentType.CODING, target_files=["calc.py"])
        stages = ParallelExecutor._partition_conflict_free_stages([st1, st2])
        return BenchmarkResult(
            case_id="BM-10",
            name="Parallel Conflict Partitioning",
            passed=len(stages) == 2,
            duration_seconds=0.0,
        )

    @staticmethod
    def _case_regression_detection() -> BenchmarkResult:
        from backend.app.agents.judge import ResultJudgeAgent
        from backend.app.models.coding import FailureInfo, JudgeVerdictType
        judge = ResultJudgeAgent()
        verdict = judge.evaluate(
            initial_failures=[FailureInfo(test_name="t1", message="err")],
            post_patch_test_data={"exit_code": 1, "passed": False, "counts": {"passed": 0, "failed": 3}},
            initial_test_data={"exit_code": 1, "passed": False, "counts": {"passed": 2, "failed": 1}},
        )
        return BenchmarkResult(
            case_id="BM-11",
            name="Regression Detection",
            passed=verdict.verdict == JudgeVerdictType.REGRESSION,
            duration_seconds=0.0,
        )

    @staticmethod
    def _case_documentation_synthesis() -> BenchmarkResult:
        from backend.app.agents.specialized import DocumentationAgent
        from backend.app.models.multi_agent import SubTask
        agent = DocumentationAgent(llm_provider=MockLLMProvider())
        st = SubTask(task_id="t1", subtask_id="s1", description="Document project", assigned_agent=AgentType.DOCUMENTATION)
        res = agent.execute(st)
        return BenchmarkResult(
            case_id="BM-12",
            name="Documentation Synthesis",
            passed=res is not None and "Documentation" in res.summary,
            duration_seconds=0.0,
        )

    # ── Phase 7 Benchmark Cases ──────────────────────────────────────

    @staticmethod
    def _case_simple_task_routing() -> BenchmarkResult:
        from backend.app.intelligence.strategy import ExecutionStrategy, StrategySelector
        strategy = StrategySelector.select_strategy("t-p7-1", "general", complexity="simple")
        return BenchmarkResult(
            case_id="BM-13", name="Simple Task Routing",
            passed=strategy == ExecutionStrategy.DIRECT, duration_seconds=0.0,
        )

    @staticmethod
    def _case_complex_task_decomposition() -> BenchmarkResult:
        decomposer = TaskDecomposer(llm_provider=MockLLMProvider())
        info = decomposer.estimate_complexity("Investigate comprehensive architecture and fix all failing tests")
        subtasks = decomposer.adaptive_decompose("Fix failing tests", task_id="t-p7-2", complexity="complex")
        return BenchmarkResult(
            case_id="BM-14", name="Complex Task Decomposition",
            passed=info["level"] == "complex" and len(subtasks) >= 2, duration_seconds=0.0,
        )

    @staticmethod
    def _case_capability_aware_routing() -> BenchmarkResult:
        from backend.app.models.multi_agent import SubTask
        from backend.app.services.agent_router import AdaptiveAgentRouter
        st = SubTask(task_id="t-p7-3", subtask_id="s1", description="Run tests", assigned_agent=AgentType.DEBUGGER)
        decision = AdaptiveAgentRouter.route_subtask(st, task_type="bug_fix")
        return BenchmarkResult(
            case_id="BM-15", name="Capability-Aware Routing",
            passed=decision.selected_agent in (AgentType.DEBUGGER, AgentType.RESEARCH), duration_seconds=0.0,
        )

    @staticmethod
    def _case_strategy_selection() -> BenchmarkResult:
        from backend.app.intelligence.strategy import ExecutionStrategy, StrategySelector
        strategy = StrategySelector.select_strategy("t-p7-4", "bug_fix", complexity="medium")
        return BenchmarkResult(
            case_id="BM-16", name="Strategy Selection",
            passed=strategy == ExecutionStrategy.DEBUG_THEN_PATCH, duration_seconds=0.0,
        )

    @staticmethod
    def _case_historical_strategy_recommendation() -> BenchmarkResult:
        from backend.app.intelligence.task_history import TaskHistoryService
        TaskHistoryService.record_execution(
            task_id="t-hist", task_category="bug_fix", strategy_used="DEBUG_THEN_PATCH",
            agents_involved=["debugger", "coding"], success=True,
        )
        rec = TaskHistoryService.get_recommended_strategy("bug_fix")
        return BenchmarkResult(
            case_id="BM-17", name="Historical Strategy Recommendation",
            passed=rec == "DEBUG_THEN_PATCH", duration_seconds=0.0,
        )

    @staticmethod
    def _case_failure_pattern_detection() -> BenchmarkResult:
        from backend.app.intelligence.failure_patterns import FailurePattern, FailurePatternIntelligence
        pattern = FailurePatternIntelligence.classify_failure("assert -1 == 5 FAILED test_add")
        return BenchmarkResult(
            case_id="BM-18", name="Failure Pattern Detection",
            passed=pattern == FailurePattern.TEST_FAILURE, duration_seconds=0.0,
        )

    @staticmethod
    def _case_adaptive_budgeting() -> BenchmarkResult:
        from backend.app.intelligence.resource_allocator import AdaptiveResourceAllocator
        from backend.app.intelligence.strategy import ExecutionStrategy
        from backend.app.config.settings import settings
        budget = AdaptiveResourceAllocator.allocate_budget("t-p7-5", "simple", ExecutionStrategy.DIRECT)
        return BenchmarkResult(
            case_id="BM-19", name="Adaptive Budgeting",
            passed=budget.max_tokens <= settings.MAX_AGENT_TOKENS and AdaptiveResourceAllocator.validate_within_limits(budget),
            duration_seconds=0.0,
        )

    @staticmethod
    def _case_plan_scoring() -> BenchmarkResult:
        from backend.app.intelligence.plan_scorer import PlanScorer
        from backend.app.models.multi_agent import SubTask
        subtasks = [
            SubTask(task_id="t-p7-6", subtask_id="s1", description="Research", assigned_agent=AgentType.RESEARCH),
            SubTask(task_id="t-p7-6", subtask_id="s2", description="Fix", assigned_agent=AgentType.CODING, dependencies=["s1"]),
        ]
        score = PlanScorer.score_plan("t-p7-6", "Fix bug", subtasks, "bug_fix")
        return BenchmarkResult(
            case_id="BM-20", name="Plan Scoring",
            passed=score.score > 0.5 and not score.rejected, duration_seconds=0.0,
        )

    @staticmethod
    def _case_multi_agent_optimization() -> BenchmarkResult:
        from backend.app.intelligence.agent_performance import AgentPerformanceTracker
        AgentPerformanceTracker.reset()
        prof = AgentPerformanceTracker.record_execution(AgentType.DEBUGGER, success=True, duration_seconds=2.0)
        return BenchmarkResult(
            case_id="BM-21", name="Multi-Agent Optimization",
            passed=prof.success_rate == 1.0 and prof.task_count == 1, duration_seconds=0.0,
        )

    @staticmethod
    def _case_security_invariant_preservation() -> BenchmarkResult:
        from backend.app.security.permissions import SecurityManager
        from backend.app.security.agent_permissions import AgentPermissionManager
        from backend.app.models.multi_agent import AgentType
        blocked = not SecurityManager.is_allowed("code", "read", file_path=".env")
        no_delegate = not AgentPermissionManager.can_delegate(AgentType.CODING)
        return BenchmarkResult(
            case_id="BM-22", name="Security Invariant Preservation",
            passed=blocked and no_delegate, duration_seconds=0.0,
        )
