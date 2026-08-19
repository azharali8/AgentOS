"""
AgentOS Phase 7 — Multi-Agent Consensus Engine.

Gathers structured outputs across specialized agents (Research, Debugger, Coding, Security, Reviewer)
to synthesize an agreement score and detect dissenting opinions.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from backend.app.models.experience import ConsensusResult
from backend.app.models.multi_agent import AgentResult, AgentType
from backend.app.services.event_service import EventService

logger = logging.getLogger("agentos.consensus")


class ConsensusEngine:
    """Evaluates cross-agent agreement, evidence consistency, and security vetoes."""

    @classmethod
    def evaluate_consensus(cls, task_id: str, results: List[AgentResult]) -> ConsensusResult:
        """Synthesize multiple agent outputs into a unified consensus result."""
        EventService.record_event(task_id, "CONSENSUS_STARTED")

        participating = [r.agent_type for r in results]
        evidence_list = [{"agent": r.agent_type.value, "summary": r.summary} for r in results]
        dissenting: List[str] = []

        # Check for security blocks (SecurityAgent is advisory veto)
        security_approved = True
        for r in results:
            if r.agent_type == AgentType.SECURITY and "risk" in r.summary.lower() and not r.evidence.get("passed", True):
                security_approved = False
                dissenting.append("SecurityAgent flagged policy violations or sensitive file exposure.")

        # Check for reviewer regression or failure flags
        for r in results:
            if r.agent_type == AgentType.REVIEWER and "fatal" in r.summary.lower():
                dissenting.append(f"ReviewerAgent reported: {r.summary}")

        agreement_score = 1.0 - (len(dissenting) * 0.25)
        agreement_score = max(0.0, min(1.0, agreement_score))

        decision = "CONSENSUS_REACHED" if agreement_score >= 0.75 and security_approved else "CONSENSUS_DISSENT"

        consensus = ConsensusResult(
            task_id=task_id,
            decision=decision,
            confidence=0.95 if agreement_score >= 0.8 else 0.7,
            agreement_score=round(agreement_score, 2),
            participating_agents=participating,
            dissenting_opinions=dissenting,
            evidence=evidence_list,
            security_approved=security_approved,
        )

        EventService.record_event(task_id, "CONSENSUS_COMPLETED", payload=consensus.model_dump(mode="json"))
        return consensus
