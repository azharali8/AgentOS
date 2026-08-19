"""
AgentOS Phase 7 - Adaptive Intelligence Manager.

Coordinates the adaptive runtime using the existing security model and bounded
heuristics. Historical data is advisory only.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from backend.app.intelligence.execution_history import ExecutionHistory
from backend.app.intelligence.experience_retriever import ExperienceRetriever
from backend.app.intelligence.learning_engine import LearningEngine
from backend.app.intelligence.failure_analyzer import FailureAnalyzer
from backend.app.intelligence.model_router import ModelRouter, ModelRoutingDecision
from backend.app.intelligence.performance_analyzer import PerformanceAnalyzer, PerformanceProfile
from backend.app.intelligence.performance_store import PerformanceStore
from backend.app.intelligence.plan_scorer import PlanScorer
from backend.app.intelligence.resource_allocator import AdaptiveResourceAllocator
from backend.app.intelligence.strategy import ExecutionStrategy, StrategySelector
from backend.app.intelligence.task_history import TaskHistoryService
from backend.app.llm.base import BaseLLMProvider
from backend.app.llm.mock import MockLLMProvider
from backend.app.models.multi_agent import SubTask
from backend.app.services.event_service import EventService
from backend.app.services.task_decomposer import TaskDecomposer


class AdaptiveAnalysisResult(BaseModel):
    task_id: str
    task_category: str
    complexity: str
    risk_level: str
    strategy: str
    model_routing: ModelRoutingDecision
    retrieved_experiences: List[Dict[str, Any]] = Field(default_factory=list)
    learning_summary: Dict[str, Any] = Field(default_factory=dict)
    learning_analysis: Dict[str, Any] = Field(default_factory=dict)
    performance_profiles: List[PerformanceProfile] = Field(default_factory=list)
    subtasks: List[Dict[str, Any]] = Field(default_factory=list)
    plan_score: Dict[str, Any] = Field(default_factory=dict)
    budget: Dict[str, Any] = Field(default_factory=dict)
    history: Dict[str, Any] = Field(default_factory=dict)
    failure_patterns: List[Dict[str, Any]] = Field(default_factory=list)
    recommendations: List[str] = Field(default_factory=list)
    learning_recommendations: List[Dict[str, Any]] = Field(default_factory=list)


class IntelligenceManager:
    """High-level adaptive orchestration facade."""

    @staticmethod
    def classify_instruction(instruction: str) -> Dict[str, str]:
        text = instruction.lower()
        if any(kw in text for kw in ("fix", "bug", "test", "debug")):
            task_category = "bug_fix"
        elif any(kw in text for kw in ("document", "readme", "guide")):
            task_category = "documentation"
        elif any(kw in text for kw in ("architect", "architecture", "investigate", "analyze")):
            task_category = "analysis"
        else:
            task_category = "general"

        risk_level = "high" if any(kw in text for kw in ("security", "credential", "production", "secret")) else "low"
        return {"task_category": task_category, "risk_level": risk_level}

    @classmethod
    def analyze_task(
        cls,
        task_id: str,
        instruction: str,
        task_category: Optional[str] = None,
        complexity: Optional[str] = None,
        risk_level: Optional[str] = None,
        llm_provider: Optional[BaseLLMProvider] = None,
    ) -> AdaptiveAnalysisResult:
        EventService.record_event(task_id, "ADAPTIVE_ANALYSIS_STARTED", payload={"task_id": task_id})

        classification = cls.classify_instruction(instruction)
        task_category = task_category or classification["task_category"]
        risk_level = risk_level or classification["risk_level"]

        complexity_info = TaskDecomposer.estimate_complexity(instruction)
        complexity = complexity or complexity_info["level"]

        retrieved_experiences = ExperienceRetriever.retrieve_relevant_experiences(
            task_id=task_id,
            task_type=task_category,
            task_complexity=complexity,
            instruction=instruction,
            limit=5,
        )
        experience_summary = ExperienceRetriever.summarize_retrieval(retrieved_experiences)

        strategy = StrategySelector.select_strategy(
            task_id=task_id,
            task_category=task_category,
            complexity=complexity,
            risk_level=risk_level,
            has_security_concerns=risk_level == "high",
            learning_summary=experience_summary,
        )

        model_routing = ModelRouter.route(
            task_id=task_id,
            task_category=task_category,
            complexity=complexity,
            token_budget=None,
            historical_success=experience_summary.get("provider_scores"),
            failure_history=experience_summary.get("failure_pattern_counts"),
        )

        decomposer = TaskDecomposer(llm_provider=llm_provider or MockLLMProvider())
        subtasks = decomposer.adaptive_decompose(
            instruction,
            task_id=task_id,
            strategy=strategy.value,
            complexity=complexity,
        )
        EventService.record_event(
            task_id=task_id,
            event_type="ADAPTIVE_PLAN_CREATED",
            payload={"subtask_count": len(subtasks), "strategy": strategy.value, "task_category": task_category},
        )

        plan_score = PlanScorer.score_plan(task_id, instruction, subtasks, task_category)
        budget = AdaptiveResourceAllocator.allocate_budget(
            task_id=task_id,
            complexity=complexity,
            strategy=strategy,
            security_sensitive=risk_level == "high",
            historical_profile=experience_summary.get("resource_profile"),
        )

        profiles = PerformanceAnalyzer.analyze(task_type=task_category)
        history = ExecutionHistory.build_knowledge_base(task_category=task_category)
        failure_patterns = [record.model_dump(mode="json") for record in FailureAnalyzer.list_patterns(limit=10)]

        learning_analysis = LearningEngine.analyze(
            task_id=task_id,
            task_type=task_category,
            task_complexity=complexity,
            instruction=instruction,
            selected_strategy=strategy.value,
            selected_model=model_routing.model,
            selected_agents=[agent.value for agent in StrategySelector.get_agent_pipeline(strategy)],
            failure_pattern=(failure_patterns[0].get("pattern") if failure_patterns else None),
            success=None,
            plan_score=plan_score.score,
            resource_budget=budget.model_dump(),
            retrieved_experiences=retrieved_experiences,
            retrieval_summary=experience_summary,
        )

        recommendations = cls._build_recommendations(
            task_category=task_category,
            complexity=complexity,
            risk_level=risk_level,
            strategy=strategy,
            model_routing=model_routing,
            plan_score=plan_score.score,
        )
        recommendations.extend([rec.recommendation for rec in learning_analysis.recommendations])

        PerformanceStore.save_task_strategy(task_id, strategy.value, {
            "task_category": task_category,
            "complexity": complexity,
            "risk_level": risk_level,
            "model": model_routing.model,
        })

        return AdaptiveAnalysisResult(
            task_id=task_id,
            task_category=task_category,
            complexity=complexity,
            risk_level=risk_level,
            strategy=strategy.value,
            model_routing=model_routing,
            retrieved_experiences=[item.model_dump(mode="json") for item in retrieved_experiences],
            learning_summary=experience_summary,
            learning_analysis=learning_analysis.model_dump(mode="json"),
            performance_profiles=profiles,
            subtasks=[subtask.model_dump(mode="json") for subtask in subtasks],
            plan_score=plan_score.model_dump(mode="json"),
            budget=budget.model_dump(),
            history=history,
            failure_patterns=failure_patterns,
            recommendations=recommendations,
            learning_recommendations=[rec.model_dump(mode="json") for rec in learning_analysis.recommendations],
        )

    @classmethod
    def get_task_insights(cls, task_id: str) -> Dict[str, Any]:
        return {
            "task_id": task_id,
            "history": TaskHistoryService.get_history(task_id),
            "strategy": PerformanceStore.get_task_strategy(task_id),
            "routing": PerformanceStore.get_task_routing(task_id),
            "evaluation": PerformanceStore.get_task_execution_evaluation(task_id),
        }

    @staticmethod
    def record_history(
        task_id: str,
        task_category: str,
        strategy: str,
        success: bool,
        agents_involved: List[str],
        duration_seconds: float = 0.0,
        iterations: int = 1,
        tools_used: Optional[List[str]] = None,
        **experience_metadata: Any,
    ) -> str:
        return TaskHistoryService.record_execution(
            task_id=task_id,
            task_category=task_category,
            strategy_used=strategy,
            agents_involved=agents_involved,
            success=success,
            duration_seconds=duration_seconds,
            iterations=iterations,
            tools_used=tools_used or [],
            **experience_metadata,
        )

    @staticmethod
    def _build_recommendations(
        task_category: str,
        complexity: str,
        risk_level: str,
        strategy: ExecutionStrategy,
        model_routing: ModelRoutingDecision,
        plan_score: float,
    ) -> List[str]:
        recommendations: List[str] = []
        if risk_level == "high":
            recommendations.append("Keep security review in the execution path.")
        if complexity == "complex" and strategy == ExecutionStrategy.DIRECT:
            recommendations.append("Prefer a decomposed strategy for complex tasks.")
        if plan_score < 0.75:
            recommendations.append("Increase plan quality by reducing unnecessary subtasks.")
        if model_routing.fallback_used:
            recommendations.append(f"Model fallback engaged to {model_routing.provider}/{model_routing.model}.")
        if not recommendations:
            recommendations.append(f"Strategy {strategy.value} looks appropriate for {task_category}.")
        return recommendations
