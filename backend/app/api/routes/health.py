from fastapi import APIRouter, HTTPException
from sqlalchemy import text
from backend.app.config.settings import settings
from backend.app.db.database import get_db_session
from backend.app.services.metrics_service import MetricsService

router = APIRouter()


@router.get("/health")
def health_check():
    """Liveness probe: verifies process is running."""
    return {"status": "ok"}


@router.get("/ready")
def readiness_check():
    """
    Readiness probe: verifies database connectivity, configuration validity,
    and LLM provider configuration syntax.
    """
    checks = {}

    # 1. Database check
    try:
        with get_db_session() as session:
            session.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as exc:
        checks["database"] = f"error: {exc}"

    # 2. Config check
    try:
        assert settings.WORKSPACE_ROOT is not None
        assert settings.DATABASE_URL is not None
        assert settings.MAX_PLAN_STEPS > 0
        checks["config"] = "ok"
    except Exception as exc:
        checks["config"] = f"error: {exc}"

    # 3. LLM provider syntax check
    try:
        assert settings.LLM_PROVIDER in ("ollama", "openai", "mock")
        checks["llm_provider"] = "ok"
    except Exception as exc:
        checks["llm_provider"] = f"error: {exc}"

    all_ok = all(v == "ok" for v in checks.values())
    if not all_ok:
        raise HTTPException(status_code=503, detail={"status": "not_ready", "checks": checks})

    return {"status": "ready", "checks": checks}


@router.get("/api/metrics")
def get_metrics():
    """Get runtime task, approval, and execution metrics."""
    return MetricsService.get_metrics()
