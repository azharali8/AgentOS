"""
AgentOS Phase 7 — Adaptive Learning & Optimization REST APIs.
"""

from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException

from backend.app.auth.service import UserRole, get_current_user, require_role
from backend.app.evaluation.agent_profiler import AgentProfiler
from backend.app.memory.experience import ExperienceMemory
from backend.app.models.experience import AgentPerformanceProfile, ExperienceRecord, FailureCategory
from backend.app.models.multi_agent import AgentType
from backend.app.services.failure_learning import FailureLearningService

learning_router = APIRouter(prefix="/learning", tags=["learning"])


@learning_router.get("/experiences", response_model=List[ExperienceRecord])
def list_experiences(
    task_type: Optional[str] = None,
    limit: int = 50,
    user=Depends(get_current_user),
) -> List[ExperienceRecord]:
    """List historical experience records."""
    if task_type:
        return ExperienceMemory.search_similar(task_type=task_type, limit=limit)
    return ExperienceMemory.list_all(limit=limit)


@learning_router.get("/experiences/{experience_id}", response_model=ExperienceRecord)
def get_experience(experience_id: str, user=Depends(get_current_user)) -> ExperienceRecord:
    rec = ExperienceMemory.get_experience(experience_id)
    if not rec:
        raise HTTPException(status_code=404, detail="Experience record not found")
    return rec


@learning_router.get("/agents/performance", response_model=List[AgentPerformanceProfile])
def list_agent_performance(user=Depends(get_current_user)) -> List[AgentPerformanceProfile]:
    """Retrieve empirical performance profiles for all specialized agents."""
    return AgentProfiler.list_profiles()


@learning_router.get("/agents/{agent_type}/performance", response_model=AgentPerformanceProfile)
def get_agent_performance(agent_type: str, user=Depends(get_current_user)) -> AgentPerformanceProfile:
    try:
        at = AgentType(agent_type.lower())
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid agent type '{agent_type}'")
    return AgentProfiler.get_profile(at)


@learning_router.get("/failures")
def get_failure_statistics(user=Depends(get_current_user)) -> Dict[str, Any]:
    """Get aggregated failure category counts."""
    return FailureLearningService.get_statistics()


@learning_router.get("/insights")
def get_learning_insights(user=Depends(get_current_user)) -> Dict[str, Any]:
    """High-level summary of system learning and adaptive optimizations."""
    return {
        "total_experiences_stored": len(ExperienceMemory.list_all(limit=1000)),
        "failure_patterns_tracked": sum(FailureLearningService.get_statistics().values()),
        "agent_profiles": len(AgentProfiler.list_profiles()),
        "adaptive_routing": "ACTIVE",
        "self_reflection": "ACTIVE",
        "consensus_engine": "ACTIVE",
    }
