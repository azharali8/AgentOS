"""
AgentOS Phase 7 — Adaptive Multi-Agent Intelligence Platform.

Provides performance tracking, intelligent routing, strategy selection,
historical intelligence, failure pattern detection, and self-evaluation.
"""

from backend.app.intelligence.agent_performance import AgentPerformanceTracker
from backend.app.intelligence.execution_history import ExecutionHistory, ExecutionHistoryRecord
from backend.app.intelligence.failure_analyzer import FailureAnalyzer, FailurePatternRecord
from backend.app.intelligence.model_router import ModelRouter, ModelRoutingDecision
from backend.app.intelligence.performance_analyzer import PerformanceAnalyzer, PerformanceProfile
from backend.app.intelligence.task_history import TaskHistoryService
from backend.app.intelligence.strategy import ExecutionStrategy, StrategySelector
from backend.app.intelligence.failure_patterns import FailurePatternIntelligence
from backend.app.intelligence.self_evaluator import SelfEvaluator
from backend.app.intelligence.resource_allocator import AdaptiveResourceAllocator
from backend.app.intelligence.plan_scorer import PlanScorer
from backend.app.intelligence.intelligence_manager import AdaptiveAnalysisResult, IntelligenceManager
from backend.app.intelligence.adaptive_memory import IntelligenceMemory

__all__ = [
    "AgentPerformanceTracker",
    "ExecutionHistory",
    "ExecutionHistoryRecord",
    "FailureAnalyzer",
    "FailurePatternRecord",
    "ModelRouter",
    "ModelRoutingDecision",
    "PerformanceAnalyzer",
    "PerformanceProfile",
    "TaskHistoryService",
    "ExecutionStrategy",
    "StrategySelector",
    "FailurePatternIntelligence",
    "SelfEvaluator",
    "AdaptiveResourceAllocator",
    "PlanScorer",
    "AdaptiveAnalysisResult",
    "IntelligenceManager",
    "IntelligenceMemory",
]
