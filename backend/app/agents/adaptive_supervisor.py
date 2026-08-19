"""
AgentOS Phase 7 - Adaptive Supervisor Agent.

Extends the existing Phase 5 SupervisorAgent with bounded adaptive analysis
helpers. This does not bypass the existing security or execution layers.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from backend.app.agents.supervisor import SupervisorAgent
from backend.app.intelligence.intelligence_manager import IntelligenceManager
from backend.app.intelligence.model_router import ModelRouter, ModelRoutingDecision
from backend.app.models.multi_agent import SubTask


class AdaptiveSupervisorAgent(SupervisorAgent):
    """SupervisorAgent with adaptive intelligence helpers."""

    def analyze_task(
        self,
        instruction: str,
        task_id: str,
        task_category: Optional[str] = None,
        complexity: Optional[str] = None,
        risk_level: Optional[str] = None,
    ) -> Dict[str, Any]:
        return IntelligenceManager.analyze_task(
            task_id=task_id,
            instruction=instruction,
            task_category=task_category,
            complexity=complexity,
            risk_level=risk_level,
        ).model_dump(mode="json")

    def route_model(
        self,
        task_id: str,
        task_category: str,
        complexity: str = "medium",
        token_budget: Optional[int] = None,
    ) -> ModelRoutingDecision:
        return ModelRouter.route(
            task_id=task_id,
            task_category=task_category,
            complexity=complexity,
            token_budget=token_budget,
        )

    def adaptive_decompose(
        self,
        instruction: str,
        task_id: str,
        strategy: str = "DIRECT",
        complexity: str = "medium",
    ) -> List[SubTask]:
        # Reuse the existing SupervisorAgent decomposition path.
        return super().adaptive_decompose(
            instruction=instruction,
            task_id=task_id,
            strategy=strategy,
            complexity=complexity,
        )
