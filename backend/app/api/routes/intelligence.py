"""
AgentOS Phase 7 - Adaptive Intelligence REST APIs.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from backend.app.auth.service import UserRole, get_current_user, require_role
from backend.app.config.settings import settings
from backend.app.evaluation.adaptive_metrics import AdaptiveMetricsCollector
from backend.app.intelligence.execution_history import ExecutionHistory
from backend.app.intelligence.model_router import ModelRouter
from backend.app.intelligence.performance_analyzer import PerformanceAnalyzer, PerformanceProfile
from backend.app.intelligence.performance_store import PerformanceStore
from backend.app.intelligence.strategy import ExecutionStrategy, StrategySelector
from backend.app.services.adaptive_service import AdaptiveService
from backend.app.security.rate_limit import RateLimiter

intelligence_router = APIRouter(prefix="/intelligence", tags=["intelligence"])


def _intelligence_user(user=Depends(get_current_user)):
    RateLimiter.check_rate_limit(f"intelligence:{user.user_id}")
    return user


class AnalyzeRequest(BaseModel):
    instruction: str
    task_id: str = "analyze-task"
    task_category: Optional[str] = None
    complexity: Optional[str] = None
    risk_level: Optional[str] = None


class AnalyzeResponse(BaseModel):
    task_id: str
    task_category: str
    complexity: str
    risk_level: str
    strategy: str
    model_routing: Dict[str, Any]
    performance_profiles: List[PerformanceProfile] = Field(default_factory=list)
    subtasks: List[Dict[str, Any]] = Field(default_factory=list)
    plan_score: float = 0.0
    plan_score_details: Dict[str, Any] = Field(default_factory=dict)
    budget: Dict[str, Any] = Field(default_factory=dict)
    history: Dict[str, Any] = Field(default_factory=dict)
    recommendations: List[str] = Field(default_factory=list)


class RoutingDecisionResponse(BaseModel):
    decision_id: str
    task_id: str
    task_category: str
    provider: str
    model: str
    reason: str
    confidence: float
    estimated_cost: float
    estimated_latency_ms: float
    fallback_used: bool
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: Optional[Any] = None


class FailurePatternResponse(BaseModel):
    category: str
    frequency: int
    affected_component: str
    previous_resolution: Optional[str] = None
    confidence: float
    pattern: str
    message: Optional[str] = None


class EvaluationResponse(BaseModel):
    evaluation_id: str
    task_id: str
    success: bool
    quality_score: float
    efficiency_score: float
    safety_score: float
    coordination_score: float
    recommendations: Any = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: Optional[Any] = None


class HistoryResponse(BaseModel):
    history_id: str
    task_id: str
    task_category: str
    strategy_used: str
    agents_involved: List[str] = Field(default_factory=list)
    success: bool
    duration_seconds: float
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: Optional[Any] = None


@intelligence_router.post("/analyze", response_model=AnalyzeResponse)
def analyze_task(req: AnalyzeRequest, user=Depends(_intelligence_user)) -> AnalyzeResponse:
    """Analyze a task and return adaptive planning recommendations."""
    analysis = AdaptiveService.analyze_task(
        task_id=req.task_id,
        instruction=req.instruction,
        task_category=req.task_category,
        complexity=req.complexity,
        risk_level=req.risk_level,
    )

    return AnalyzeResponse(
        task_id=analysis["task_id"],
        task_category=analysis["task_category"],
        complexity=analysis["complexity"],
        risk_level=analysis["risk_level"],
        strategy=analysis["strategy"],
        model_routing=analysis["model_routing"].model_dump(mode="json"),
        performance_profiles=analysis["performance_profiles"],
        subtasks=analysis["subtasks"],
        plan_score=analysis["plan_score"].get("score", 0.0),
        plan_score_details=analysis["plan_score"],
        budget=analysis["budget"],
        history=analysis["history"],
        recommendations=analysis["recommendations"],
    )


@intelligence_router.get("/performance", response_model=List[PerformanceProfile])
def list_performance(
    task_type: Optional[str] = None,
    agent_type: Optional[str] = None,
    model: Optional[str] = None,
    limit: int = Query(50, ge=1, le=200),
    user=Depends(require_role(UserRole.DEVELOPER)),
) -> List[PerformanceProfile]:
    return PerformanceAnalyzer.analyze(task_type=task_type, agent_type=agent_type, model=model, limit=limit)


@intelligence_router.get("/routing", response_model=List[RoutingDecisionResponse])
def list_routing(
    task_id: Optional[str] = None,
    limit: int = Query(50, ge=1, le=200),
    user=Depends(require_role(UserRole.DEVELOPER)),
) -> List[RoutingDecisionResponse]:
    if task_id:
        decision = PerformanceStore.get_task_routing(task_id)
        return [RoutingDecisionResponse(**decision)] if decision else []
    return [RoutingDecisionResponse(**row) for row in PerformanceStore.list_routing_decisions(limit=limit)]


@intelligence_router.get("/failures", response_model=List[FailurePatternResponse])
def list_failures(
    limit: int = Query(50, ge=1, le=200),
    user=Depends(require_role(UserRole.DEVELOPER)),
) -> List[FailurePatternResponse]:
    return [FailurePatternResponse(**row) for row in AdaptiveService.list_failures(limit=limit)]


@intelligence_router.get("/evaluations", response_model=List[EvaluationResponse])
def list_evaluations(
    task_id: Optional[str] = None,
    limit: int = Query(50, ge=1, le=200),
    user=Depends(require_role(UserRole.DEVELOPER)),
) -> List[EvaluationResponse]:
    if task_id:
        evaluation = PerformanceStore.get_task_execution_evaluation(task_id)
        return [EvaluationResponse(**evaluation)] if evaluation else []
    return [EvaluationResponse(**row) for row in AdaptiveService.list_evaluations(limit=limit)]


@intelligence_router.get("/plans")
def list_plans(
    task_id: Optional[str] = None,
    limit: int = Query(50, ge=1, le=200),
    user=Depends(require_role(UserRole.DEVELOPER)),
) -> List[Dict[str, Any]]:
    plans = AdaptiveService.list_plans(limit=limit)
    if task_id:
        plans = [plan for plan in plans if plan.get("task_id") == task_id]
    return plans


@intelligence_router.get("/history", response_model=List[HistoryResponse])
def list_history(
    task_id: Optional[str] = None,
    limit: int = Query(50, ge=1, le=200),
    user=Depends(require_role(UserRole.DEVELOPER)),
) -> List[HistoryResponse]:
    history = AdaptiveService.list_history(limit=limit)
    if task_id:
        history = [row for row in history if row.get("task_id") == task_id]
    return [HistoryResponse(**row) for row in history]


@intelligence_router.get("/tasks/{task_id}")
def get_task_intelligence(task_id: str, user=Depends(_intelligence_user)) -> Dict[str, Any]:
    insight = AdaptiveService.get_task_insights(task_id)
    if not any(insight.values()):
        raise HTTPException(status_code=404, detail="Task intelligence not found")
    return insight


@intelligence_router.get("/tasks/{task_id}/strategy")
def get_task_strategy(task_id: str, user=Depends(_intelligence_user)) -> Dict[str, Any]:
    strategy = PerformanceStore.get_task_strategy(task_id)
    if not strategy:
        raise HTTPException(status_code=404, detail="Strategy not found for task")
    return strategy


@intelligence_router.get("/tasks/{task_id}/performance")
def get_task_performance(task_id: str, user=Depends(_intelligence_user)) -> Dict[str, Any]:
    history = PerformanceStore.get_task_history(task_id)
    if not history:
        raise HTTPException(status_code=404, detail="Performance data not found")
    return {
        "task_id": task_id,
        "history": history,
        "performance_profiles": [profile.model_dump(mode="json") for profile in PerformanceAnalyzer.analyze(task_type=history.get("task_category"))],
    }


@intelligence_router.get("/tasks/{task_id}/evaluation")
def get_task_evaluation(task_id: str, user=Depends(_intelligence_user)) -> Dict[str, Any]:
    evaluation = PerformanceStore.get_task_execution_evaluation(task_id)
    if not evaluation:
        raise HTTPException(status_code=404, detail="Evaluation not found")
    return {"task_id": task_id, "evaluation": evaluation}


@intelligence_router.get("/tasks/{task_id}/routing")
def get_task_routing(task_id: str, user=Depends(_intelligence_user)) -> Dict[str, Any]:
    routing = PerformanceStore.get_task_routing(task_id)
    if not routing:
        raise HTTPException(status_code=404, detail="Routing not found for task")
    return routing


@intelligence_router.get("/strategies")
def list_strategies(user=Depends(_intelligence_user)) -> Dict[str, Any]:
    return {
        "available_strategies": [s.value for s in ExecutionStrategy],
        "strategy_agents": {
            s.value: [a.value for a in StrategySelector.get_agent_pipeline(s)]
            for s in ExecutionStrategy
        },
        "metrics": AdaptiveMetricsCollector.get_metrics_snapshot().get("adaptive", {}),
    }
