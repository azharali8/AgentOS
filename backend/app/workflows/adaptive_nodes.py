"""
AgentOS Phase 7 — Adaptive Intelligence LangGraph Nodes.

Implements the full adaptive multi-agent pipeline:
classify → complexity → historical → strategy → decompose → score → route →
allocate → execute → aggregate → evaluate → learn → final_response
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List

from backend.app.agents.supervisor import SupervisorAgent
from backend.app.agents.task_classifier import TaskClassifierAgent
from backend.app.intelligence.adaptive_memory import IntelligenceMemory, MemoryCategory
from backend.app.intelligence.agent_performance import AgentPerformanceTracker
from backend.app.evaluation.adaptive_metrics import AdaptiveMetricsCollector
from backend.app.intelligence.experience_retriever import ExperienceRetriever
from backend.app.intelligence.learning_engine import LearningEngine
from backend.app.intelligence.model_router import ModelRouter
from backend.app.intelligence.plan_scorer import PlanScorer
from backend.app.intelligence.resource_allocator import AdaptiveResourceAllocator
from backend.app.intelligence.self_evaluator import SelfEvaluator
from backend.app.intelligence.strategy import ExecutionStrategy, StrategySelector
from backend.app.intelligence.task_history import TaskHistoryService
from backend.app.llm.factory import get_llm_provider
from backend.app.models.multi_agent import AgentType, SubTask
from backend.app.services.agent_budget import AgentBudgetTracker
from backend.app.services.agent_router import AdaptiveAgentRouter
from backend.app.services.event_service import EventService
from backend.app.workflows.adaptive_state import AdaptiveState

logger = logging.getLogger("agentos.adaptive_nodes")


def classify_node(state: AdaptiveState) -> Dict[str, Any]:
    task_id = state.get("task_id", "task-1")
    instruction = state.get("user_instruction", "")
    classifier = TaskClassifierAgent(llm_provider=get_llm_provider())
    result = classifier.classify(instruction)
    category = result.task_type.value if hasattr(result, "task_type") else "general"
    EventService.record_event(task_id, "ADAPTIVE_TASK_STARTED", payload={"category": category})
    return {"task_category": category, "status": "CLASSIFYING"}


def complexity_analysis_node(state: AdaptiveState) -> Dict[str, Any]:
    task_id = state.get("task_id", "task-1")
    instruction = state.get("user_instruction", "").lower()
    word_count = len(instruction.split())

    if word_count < 10 and not any(kw in instruction for kw in ("fix", "debug", "investigate", "architecture")):
        complexity = "simple"
    elif any(kw in instruction for kw in ("architecture", "comprehensive", "investigate", "report")):
        complexity = "complex"
    else:
        complexity = "medium"

    risk = "high" if any(kw in instruction for kw in ("security", "credential", "production")) else "low"

    EventService.record_event(task_id, "TASK_COMPLEXITY_ANALYZED", payload={"complexity": complexity, "risk": risk})
    return {"complexity": complexity, "risk_level": risk}


def retrieve_experience_node(state: AdaptiveState) -> Dict[str, Any]:
    task_id = state.get("task_id", "task-1")
    instruction = state.get("user_instruction", "")
    category = state.get("task_category", "general")
    complexity = state.get("complexity", "medium")

    retrieved = ExperienceRetriever.retrieve_relevant_experiences(
        task_id=task_id,
        task_type=category,
        task_complexity=complexity,
        instruction=instruction,
        limit=5,
    )
    summary = ExperienceRetriever.summarize_retrieval(retrieved)

    EventService.record_event(
        task_id,
        "EXPERIENCE_RETRIEVED",
        payload={
            "retrieved_count": len(retrieved),
            "recommended_strategy": summary.get("recommended_strategy"),
            "average_confidence": summary.get("average_confidence", 0.0),
        },
    )
    return {
        "retrieved_experiences": [item.model_dump(mode="json") for item in retrieved],
        "experience_summary": summary,
        "status": "HISTORICAL_CONTEXT_RETRIEVED",
    }


def historical_analysis_node(state: AdaptiveState) -> Dict[str, Any]:
    task_id = state.get("task_id", "task-1")
    category = state.get("task_category", "general")
    similar = TaskHistoryService.get_similar_executions(category, limit=3)
    recommended = TaskHistoryService.get_recommended_strategy(category)
    experience_summary = state.get("experience_summary", {})
    EventService.record_event(
        task_id, "HISTORICAL_CONTEXT_RETRIEVED",
        payload={
            "similar_count": len(similar),
            "recommended_strategy": recommended,
            "retrieved_count": len(state.get("retrieved_experiences", [])),
        },
    )
    return {
        "status": "PLANNING",
        "history": {
            "similar_count": len(similar),
            "recommended_strategy": recommended,
            "task_category": category,
        },
        "learning_summary": experience_summary,
    }


def strategy_selection_node(state: AdaptiveState) -> Dict[str, Any]:
    task_id = state.get("task_id", "task-1")
    strategy = StrategySelector.select_strategy(
        task_id=task_id,
        task_category=state.get("task_category", "general"),
        complexity=state.get("complexity", "medium"),
        risk_level=state.get("risk_level", "low"),
        has_security_concerns=state.get("risk_level") == "high",
        learning_summary=state.get("experience_summary", {}),
    )
    from backend.app.intelligence.performance_store import PerformanceStore
    PerformanceStore.save_task_strategy(task_id, strategy.value, {"complexity": state.get("complexity")})
    AdaptiveMetricsCollector.record_strategy_selected()
    return {"strategy": strategy.value}


def route_model_node(state: AdaptiveState) -> Dict[str, Any]:
    task_id = state.get("task_id", "task-1")
    summary = state.get("experience_summary", {})
    routing = ModelRouter.route(
        task_id=task_id,
        task_category=state.get("task_category", "general"),
        complexity=state.get("complexity", "medium"),
        historical_success=summary.get("provider_scores"),
        failure_history=summary.get("failure_pattern_counts"),
    )
    AdaptiveMetricsCollector.record_model_routed()
    return {"model_routing": routing.model_dump(mode="json")}


def decompose_node(state: AdaptiveState) -> Dict[str, Any]:
    task_id = state.get("task_id", "task-1")
    instruction = state.get("user_instruction", "")
    supervisor = SupervisorAgent()
    subtasks = supervisor.adaptive_decompose(
        instruction, task_id=task_id,
        strategy=state.get("strategy", "DIRECT"),
        complexity=state.get("complexity", "medium"),
    )
    return {"subtasks": [st.model_dump() for st in subtasks], "status": "DECOMPOSED"}


def score_plan_node(state: AdaptiveState) -> Dict[str, Any]:
    task_id = state.get("task_id", "task-1")
    instruction = state.get("user_instruction", "")
    subtasks = [SubTask(**s) for s in state.get("subtasks", [])]
    score = PlanScorer.score_plan(task_id, instruction, subtasks, state.get("task_category", "general"))
    AdaptiveMetricsCollector.record_plan_scored()
    return {"plan_score": score.model_dump(mode="json")}


def route_agents_node(state: AdaptiveState) -> Dict[str, Any]:
    task_id = state.get("task_id", "task-1")
    summary = state.get("experience_summary", {})
    decisions = []
    subtasks = [SubTask(**s) for s in state.get("subtasks", [])]
    for st in subtasks:
        decision = AdaptiveAgentRouter.route_subtask(
            st,
            task_type=state.get("task_category", "general"),
            historical_profile=summary.get("agent_scores"),
            learning_recommendations=state.get("learning_recommendations", []),
        )
        decisions.append(decision.model_dump(mode="json"))
        EventService.record_event(task_id, "AGENT_ROUTED", payload={"agent": decision.selected_agent.value})
    return {"routing_decisions": decisions}


def allocate_budget_node(state: AdaptiveState) -> Dict[str, Any]:
    task_id = state.get("task_id", "task-1")
    try:
        strategy = ExecutionStrategy(state.get("strategy", "DIRECT"))
    except ValueError:
        strategy = ExecutionStrategy.DIRECT
    summary = state.get("experience_summary", {})

    budget = AdaptiveResourceAllocator.allocate_budget(
        task_id=task_id,
        complexity=state.get("complexity", "medium"),
        strategy=strategy,
        security_sensitive=state.get("risk_level") == "high",
        historical_profile=summary.get("resource_profile"),
    )
    AgentBudgetTracker.initialize_task(task_id, budget)
    return {"budget": budget.model_dump()}


def execute_node(state: AdaptiveState) -> Dict[str, Any]:
    task_id = state.get("task_id", "task-1")
    subtasks_raw = state.get("subtasks", [])
    completed_ids = set(state.get("completed_subtask_ids", []))
    subtask_results = dict(state.get("subtask_results", {}))
    iteration = int(state.get("iteration", 0)) + 1

    EventService.record_event(task_id, "EXECUTION_STRATEGY_STARTED", payload={"strategy": state.get("strategy")})

    supervisor = SupervisorAgent()
    runnable: List[SubTask] = []
    for st_dict in subtasks_raw:
        st = SubTask(**st_dict)
        if st.subtask_id in completed_ids:
            continue
        if all(dep in completed_ids for dep in st.dependencies):
            runnable.append(st)

    if not runnable:
        EventService.record_event(task_id, "ADAPTIVE_REPLAN", payload={"reason": "no_runnable_subtasks", "iteration": iteration})
        return {
            "iteration": iteration,
            "execution_blocked": True,
            "status": "BLOCKED",
        }

    batch_results = supervisor.executor.execute_batch(
        subtasks=runnable, runner_fn=supervisor.execute_subtask, task_id=task_id,
    )

    for result in batch_results:
        subtask_results[result.subtask_id] = result.model_dump()
        completed_ids.add(result.subtask_id)
        AgentPerformanceTracker.record_execution(
            agent_type=result.agent_type,
            success=result.status.value == "completed",
            task_type=state.get("task_category", "general"),
        )

    has_coding = any(SubTask(**s).assigned_agent == AgentType.CODING for s in subtasks_raw)
    return {
        "iteration": iteration,
        "completed_subtask_ids": list(completed_ids),
        "subtask_results": subtask_results,
        "approval_required": has_coding,
        "approval_id": f"appr-{task_id[:8]}-adaptive" if has_coding else None,
        "execution_blocked": False,
        "status": "EXECUTING",
    }


def aggregate_node(state: AdaptiveState) -> Dict[str, Any]:
    from backend.app.services.result_aggregator import ResultAggregator
    task_id = state.get("task_id", "task-1")
    subtask_results = state.get("subtask_results", {})
    results = []
    for sid, rdict in subtask_results.items():
        from backend.app.models.multi_agent import AgentResult, AgentStatus
        results.append(AgentResult(
            subtask_id=sid,
            agent_type=AgentType(rdict.get("agent_type", "research")),
            status=AgentStatus(rdict.get("status", "completed")),
            summary=rdict.get("summary", ""),
        ))
    aggregated = ResultAggregator.aggregate(results)
    return {"aggregated_results": aggregated}


def evaluate_node(state: AdaptiveState) -> Dict[str, Any]:
    task_id = state.get("task_id", "task-1")
    success = state.get("aggregated_results", {}).get("all_succeeded", False)
    evaluation = SelfEvaluator.evaluate_task(
        task_id=task_id,
        instruction=state.get("user_instruction", ""),
        subtask_results=state.get("subtask_results", {}),
        success=success,
        strategy=state.get("strategy", "DIRECT"),
        agents_used=[d.get("selected_agent", "") for d in state.get("routing_decisions", [])],
    )
    AdaptiveMetricsCollector.record_evaluation()
    return {"evaluation": evaluation.model_dump(mode="json")}


def learn_node(state: AdaptiveState) -> Dict[str, Any]:
    task_id = state.get("task_id", "task-1")
    success = state.get("aggregated_results", {}).get("all_succeeded", False)
    strategy = state.get("strategy", "DIRECT")
    selected_agents = [d.get("selected_agent", "") for d in state.get("routing_decisions", [])]
    learning_analysis = LearningEngine.analyze(
        task_id=task_id,
        task_type=state.get("task_category", "general"),
        task_complexity=state.get("complexity", "medium"),
        instruction=state.get("user_instruction", ""),
        selected_strategy=strategy,
        selected_model=state.get("model_routing", {}).get("model"),
        selected_agents=selected_agents,
        failure_pattern=(state.get("failure_patterns", [{}])[0].get("pattern") if state.get("failure_patterns") else None),
        success=success,
        plan_score=float((state.get("plan_score") or {}).get("score", 0.0)),
        resource_budget=state.get("budget", {}),
        retrieved_experiences=state.get("retrieved_experiences", []),
        retrieval_summary=state.get("experience_summary", {}),
    )

    if any(
        isinstance(rec, dict) and rec.get("target_strategy") == strategy
        for rec in learning_analysis.model_dump(mode="json").get("recommendations", [])
    ):
        AdaptiveMetricsCollector.record_learning_recommendation_applied(success=success)

    history_id = TaskHistoryService.record_execution(
        task_id=task_id,
        task_category=state.get("task_category", "general"),
        strategy_used=strategy,
        agents_involved=selected_agents,
        success=success,
        duration_seconds=float((state.get("budget") or {}).get("max_execution_time", 0.0) or 0.0),
        iterations=int(state.get("iteration", 1) or 1),
        tools_used=[str(tool) for tool in state.get("tools_used", [])],
        task_description=state.get("user_instruction", ""),
        task_complexity=state.get("complexity", "medium"),
        project_type=state.get("project_type", "python"),
        selected_provider=state.get("model_routing", {}).get("provider"),
        selected_model=state.get("model_routing", {}).get("model"),
        selected_agents=selected_agents,
        decomposition_summary=[st.get("description", "") for st in state.get("subtasks", [])],
        plan_score=float((state.get("plan_score") or {}).get("score", 0.0)),
        resource_budget=state.get("budget", {}),
        approval_required=bool(state.get("approval_required", False)),
        approval_outcome=state.get("approval_status"),
        failure_pattern=(state.get("failure_patterns", [{}])[0].get("pattern") if state.get("failure_patterns") else None),
        evaluation_score=float((state.get("evaluation") or {}).get("overall_quality", 0.0)),
        final_outcome="SUCCESS" if success else "FAILED",
        learning_metadata={
            "learning_recommendations": learning_analysis.model_dump(mode="json").get("recommendations", []),
            "learning_summary": learning_analysis.summary,
            "retrieved_count": learning_analysis.retrieved_count,
        },
    )
    IntelligenceMemory.store(
        MemoryCategory.SUCCESSFUL_STRATEGY if success else MemoryCategory.FAILED_STRATEGY,
        key=strategy,
        value={"task_category": state.get("task_category"), "complexity": state.get("complexity")},
        task_id=task_id,
    )
    if success:
        AdaptiveMetricsCollector.record_adaptive_task_completed()
    else:
        AdaptiveMetricsCollector.record_replan()
    EventService.record_event(
        task_id,
        "ADAPTIVE_TASK_COMPLETED",
        payload={
            "success": success,
            "history_id": history_id,
            "learning_recommendations": len(learning_analysis.recommendations),
        },
    )
    return {
        "status": "LEARNED",
        "learning_analysis": learning_analysis.model_dump(mode="json"),
        "learning_recommendations": [rec.model_dump(mode="json") for rec in learning_analysis.recommendations],
        "recorded_experience_id": history_id,
    }


def record_experience_node(state: AdaptiveState) -> Dict[str, Any]:
    task_id = state.get("task_id", "task-1")
    recorded_experience_id = state.get("recorded_experience_id")
    if state.get("learning_analysis"):
        LearningEngine.update_experience(
            task_id,
            {
                "learning_metadata": {
                    "recorded_experience_id": recorded_experience_id,
                    "learning_analysis": state.get("learning_analysis", {}),
                    "learning_recommendations": state.get("learning_recommendations", []),
                }
            },
            create_if_missing=False,
        )

    return {
        "status": "RECORDED",
        "recorded_experience_id": recorded_experience_id,
    }


def final_response_node(state: AdaptiveState) -> Dict[str, Any]:
    supervisor = SupervisorAgent()
    response = supervisor.synthesize_response(
        state.get("user_instruction", ""),
        state.get("aggregated_results", {}),
        state.get("task_id", "task-1"),
    )
    eval_data = state.get("evaluation", {})
    if eval_data:
        response += f"\nSelf-Evaluation Quality: {eval_data.get('overall_quality', 'N/A')}\n"
        response += f"Recommended Strategy: {eval_data.get('recommended_strategy', 'N/A')}\n"
    return {"final_response": response, "status": "COMPLETED"}
