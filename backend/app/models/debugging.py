"""
AgentOS Phase 4 — Debugging state tracking and execution metrics models.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class DebugIterationRecord(BaseModel):
    """Record of a single debug iteration in the autonomous coding loop."""
    iteration: int
    attempt: int
    diagnosis: Optional[Dict[str, Any]] = None
    patch_id: Optional[str] = None
    patch_hash: Optional[str] = None
    approval_id: Optional[str] = None
    test_result_summary: Optional[Dict[str, Any]] = None
    verdict: Optional[str] = None
    rollback_applied: bool = False
    timestamp: str = ""


class CodingWorkflowMetrics(BaseModel):
    """Aggregate observability metrics for the coding workflow."""
    coding_tasks_total: int = 0
    coding_tasks_success: int = 0
    coding_tasks_failed: int = 0
    coding_tasks_rolled_back: int = 0
    total_debug_iterations: int = 0
    average_debug_iterations: float = 0.0
    regression_count: int = 0
    approval_rejection_count: int = 0
