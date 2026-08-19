"""
Unit and integration tests for Phase 7 Adaptive Intelligence & Learning.
"""

from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from backend.app.agents.reflection import ReflectionEngine
from backend.app.evaluation.agent_profiler import AgentProfiler
from backend.app.main import app
from backend.app.memory.experience import ExperienceMemory
from backend.app.models.experience import (
    AgentPerformanceProfile,
    ConsensusResult,
    ExperienceRecord,
    FailureCategory,
    ReflectionResult,
    RoutingDecision,
)
from backend.app.models.multi_agent import AgentResult, AgentStatus, AgentType, SubTask
from backend.app.services.agent_router import AdaptiveAgentRouter
from backend.app.services.consensus import ConsensusEngine
from backend.app.services.failure_learning import FailureLearningService

client = TestClient(app)


# ── 1. Experience Memory Tests ────────────────────────────────────────

def test_experience_memory_storage_and_retrieval():
    ExperienceMemory.reset()
    rec = ExperienceRecord(
        experience_id="exp-1",
        task_id="task-1",
        task_type="bug_fix",
        instruction_summary="Fix calculator subtract bug",
        strategy="RESEARCH_DEBUG_CODE_REVIEW",
        success=True,
        iterations=1,
    )
    ExperienceMemory.store_experience(rec)

    fetched = ExperienceMemory.get_experience("exp-1")
    assert fetched is not None
    assert fetched.task_type == "bug_fix"

    similar = ExperienceMemory.search_similar(task_type="bug_fix")
    assert len(similar) == 1
    assert similar[0].experience_id == "exp-1"

    strategies = ExperienceMemory.get_successful_strategies("bug_fix")
    assert "RESEARCH_DEBUG_CODE_REVIEW" in strategies


# ── 2. Experience Secret Sanitization ─────────────────────────────────

def test_experience_memory_redacts_secrets():
    ExperienceMemory.reset()
    rec = ExperienceRecord(
        experience_id="exp-sec",
        task_id="task-sec",
        task_type="bug_fix",
        instruction_summary="Use token ghp_123456789012345678901234567890123456 to fix code",
        lessons_learned=["Found sk-1234567890abcdef1234567890abcdef in config"],
        success=True,
    )
    ExperienceMemory.store_experience(rec)

    stored = ExperienceMemory.get_experience("exp-sec")
    assert stored is not None
    assert "[REDACTED_SECRET]" in stored.instruction_summary
    assert "ghp_" not in stored.instruction_summary
    assert "[REDACTED_SECRET]" in stored.lessons_learned[0]
    assert "sk-" not in stored.lessons_learned[0]


# ── 3. Agent Performance Profiling Tests ──────────────────────────────

def test_agent_performance_profiling():
    AgentProfiler.reset()
    prof1 = AgentProfiler.record_execution(
        agent_type=AgentType.DEBUGGER,
        success=True,
        duration_seconds=2.5,
        tokens_used=150,
        tool_calls=2,
    )
    assert prof1.task_count == 1
    assert prof1.success_rate == 1.0

    prof2 = AgentProfiler.record_execution(
        agent_type=AgentType.DEBUGGER,
        success=False,
        duration_seconds=3.5,
        tokens_used=200,
        tool_calls=1,
    )
    assert prof2.task_count == 2
    assert prof2.success_rate == 0.5


# ── 4. Adaptive Agent Router Tests ────────────────────────────────────

def test_adaptive_agent_router():
    AgentProfiler.reset()
    st = SubTask(
        task_id="t-route",
        subtask_id="s1",
        description="Inspect codebase symbols",
        assigned_agent=AgentType.RESEARCH,
        target_files=["calc.py"],
    )
    decision = AdaptiveAgentRouter.route_subtask(st, task_type="analysis")
    assert decision.selected_agent in (AgentType.RESEARCH, AgentType.CODING)
    assert decision.confidence >= 0.8


# ── 5. Failure Pattern Learning Tests ─────────────────────────────────

def test_failure_pattern_learning():
    FailureLearningService.reset()
    FailureLearningService.record_failure(
        task_id="t-fail",
        category=FailureCategory.TEST_FAILURE,
        message="assert -1 == 5",
        resolution="Change subtraction operator to addition in add() function",
    )

    resolutions = FailureLearningService.get_resolutions_for_category(FailureCategory.TEST_FAILURE)
    assert len(resolutions) == 1
    assert "subtraction" in resolutions[0]


# ── 6. Self-Reflection Engine Tests ───────────────────────────────────

def test_self_reflection_engine():
    res = ReflectionEngine.reflect_on_task(
        task_id="t-reflect",
        instruction="Fix add function",
        subtask_results={"s1": {"status": "completed"}},
        success=True,
        iterations=1,
    )
    assert res.overall_quality >= 0.9
    assert len(res.lessons) >= 1
    assert "RESEARCH_DEBUG_CODE_REVIEW" in res.recommended_strategy


# ── 7. Multi-Agent Consensus Engine Tests ─────────────────────────────

def test_consensus_engine():
    results = [
        AgentResult(subtask_id="s1", agent_type=AgentType.RESEARCH, status=AgentStatus.COMPLETED, summary="Found bug in add"),
        AgentResult(subtask_id="s2", agent_type=AgentType.CODING, status=AgentStatus.COMPLETED, summary="Applied patch"),
        AgentResult(subtask_id="s3", agent_type=AgentType.SECURITY, status=AgentStatus.COMPLETED, summary="All checks passed", evidence={"passed": True}),
    ]
    consensus = ConsensusEngine.evaluate_consensus("t-cons", results)
    assert consensus.decision == "CONSENSUS_REACHED"
    assert consensus.agreement_score >= 0.8
    assert consensus.security_approved is True


# ── 8. Phase 7 Learning REST API Tests ────────────────────────────────

def test_learning_api_endpoints():
    ExperienceMemory.reset()
    ExperienceMemory.store_experience(ExperienceRecord(
        experience_id="exp-api",
        task_id="t-api",
        task_type="bug_fix",
        instruction_summary="API test",
        success=True,
    ))

    # 1. List experiences
    resp = client.get("/api/learning/experiences")
    assert resp.status_code == 200
    assert len(resp.json()) >= 1

    # 2. Get specific experience
    resp = client.get("/api/learning/experiences/exp-api")
    assert resp.status_code == 200
    assert resp.json()["experience_id"] == "exp-api"

    # 3. Agent performance
    resp = client.get("/api/learning/agents/performance")
    assert resp.status_code == 200
    assert len(resp.json()) >= 1

    # 4. Learning insights summary
    resp = client.get("/api/learning/insights")
    assert resp.status_code == 200
    assert resp.json()["adaptive_routing"] == "ACTIVE"
