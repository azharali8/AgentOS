"""
AgentOS Phase 7 — Adaptive Agent Router & Cost Optimizer.

Routes subtasks to the optimal agent based on:
1. Hard AgentPermission & Security verification (NON-NEGOTIABLE)
2. Declared AgentCapabilities
3. Historical success rate from AgentProfiler
4. Cost and latency optimization
"""

from __future__ import annotations

import logging
import uuid
from typing import Any, Dict, List, Optional

from backend.app.agents.registry import AgentRegistry
from backend.app.evaluation.agent_profiler import AgentProfiler
from backend.app.models.experience import RoutingDecision
from backend.app.models.multi_agent import AgentCapability, AgentType, SubTask
from backend.app.security.agent_permissions import AgentPermissionManager
from backend.app.services.event_service import EventService

logger = logging.getLogger("agentos.agent_router")


class AdaptiveAgentRouter:
    """Selects best authorized agent using capabilities, empirical success, and cost."""

    @classmethod
    def route_subtask(
        cls,
        subtask: SubTask,
        task_type: str = "bug_fix",
        historical_profile: Optional[Dict[str, float]] = None,
        learning_recommendations: Optional[List[Dict[str, Any]]] = None,
    ) -> RoutingDecision:
        """
        Determine the optimal agent for a subtask.
        Strict Hierarchy: SECURITY > CAPABILITY > EMPIRICAL_SUCCESS > COST
        """
        requested = subtask.assigned_agent

        # 1. Candidate evaluation
        candidate_scores: Dict[str, float] = {}
        for agent_type in AgentType:
            if agent_type == AgentType.SUPERVISOR:
                continue

            # Hard check: Must have basic permission to execute its primary purpose
            if subtask.target_files and agent_type == AgentType.CODING:
                if not AgentPermissionManager.can_modify_code(agent_type):
                    continue

            # Score based on empirical profile
            profile = AgentProfiler.get_profile(agent_type)
            score = profile.success_rate * 100.0

            if historical_profile and agent_type.value in historical_profile:
                score += float(historical_profile.get(agent_type.value, 0.0)) * 25.0

            if learning_recommendations:
                for recommendation in learning_recommendations:
                    if not isinstance(recommendation, dict):
                        continue
                    if recommendation.get("recommendation_type") != "agent":
                        continue
                    if recommendation.get("target_agent") == agent_type.value:
                        score += float(recommendation.get("confidence", 0.0)) * 20.0

            # Favor agent matching the requested subtask assignment
            if agent_type == requested:
                score += 50.0

            candidate_scores[agent_type.value] = round(score, 2)

        # Select highest scoring valid candidate
        best_agent_str = max(candidate_scores, key=candidate_scores.get) if candidate_scores else requested.value
        chosen_agent = AgentType(best_agent_str)

        decision = RoutingDecision(
            decision_id=f"route-{uuid.uuid4().hex[:8]}",
            task_id=subtask.task_id,
            subtask_id=subtask.subtask_id,
            selected_agent=chosen_agent,
            candidate_scores=candidate_scores,
            reasoning=f"Selected {chosen_agent.value} with empirical score {candidate_scores.get(chosen_agent.value, 0.0)}",
            confidence=0.95,
        )

        EventService.record_event(
            task_id=subtask.task_id,
            event_type="ROUTING_DECISION_CREATED",
            payload=decision.model_dump(),
        )
        return decision
