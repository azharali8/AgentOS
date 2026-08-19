"""
AgentOS Phase 5 — Result Aggregator.

Consolidates outputs from multiple specialized agents:
- Collects results and extracts evidence
- Detects conflicting findings or contradictory verdicts
- Formats structured engineering summaries
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from backend.app.models.multi_agent import AgentResult, AgentStatus

logger = logging.getLogger("agentos.result_aggregator")


class ResultAggregator:
    """Aggregates subtask execution results and flags discrepancies."""

    @staticmethod
    def aggregate(results: List[AgentResult]) -> Dict[str, Any]:
        """Synthesize multiple AgentResults into a coherent report."""
        total = len(results)
        completed = [r for r in results if r.status == AgentStatus.COMPLETED]
        failed = [r for r in results if r.status == AgentStatus.FAILED]

        files_modified = set()
        for r in results:
            files_modified.update(r.files_modified)

        evidence_combined: Dict[str, Any] = {}
        for r in results:
            evidence_combined[r.subtask_id] = {
                "agent": r.agent_type.value,
                "summary": r.summary,
                "evidence": r.evidence,
            }

        conflicts = []
        # Basic conflict check: multiple agents asserting contradictory outcomes on same subtask
        summaries = [r.summary.lower() for r in results]
        if any("regression" in s for s in summaries) and any("success" in s for s in summaries):
            conflicts.append("Conflicting verdicts detected across agents (Success vs Regression).")

        return {
            "total_subtasks": total,
            "completed_count": len(completed),
            "failed_count": len(failed),
            "files_modified": list(files_modified),
            "conflicts": conflicts,
            "evidence": evidence_combined,
            "all_succeeded": len(failed) == 0 and total > 0,
        }
