from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.responses import JSONResponse
import logging
import time

from backend.app.api.routes.health import router as health_router
from backend.app.api.routes.tools import router as tools_router
from backend.app.api.routes.agent import router as agent_router
from backend.app.api.routes.tasks import router as tasks_router
from backend.app.api.routes.approvals import router as approvals_router
from backend.app.api.routes.coding import router as coding_router
from backend.app.api.routes.dashboard import dashboard_router, system_router
from backend.app.api.routes.learning import learning_router
from backend.app.api.routes.intelligence import intelligence_router
from backend.app.api.routes.multi_agent import agents_router, multi_agent_router
from backend.app.observability.correlation import CorrelationMiddleware
from backend.app.services.recovery_service import RecoveryService

import backend.app.tools.filesystem  # trigger registration
import backend.app.tools.terminal  # trigger registration
import backend.app.tools.code_tools  # trigger registration
import backend.app.tools.git  # trigger registration
from backend.app.config.settings import settings
from fastapi.middleware.cors import CORSMiddleware

logger = logging.getLogger(__name__)

_startup_time = time.time()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup recovery
    try:
        summary = RecoveryService.recover_tasks_on_startup()
        logger.info("Startup task recovery complete: %s", summary)
    except Exception as exc:
        logger.warning("Startup recovery encountered an error: %s", exc)
    yield
    # Shutdown logic if any


app = FastAPI(title="AgentOS", version="0.3.0", lifespan=lifespan)
app.add_middleware(CorrelationMiddleware)

# CORS configuration – allow local development origins only
from fastapi.middleware.cors import CORSMiddleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
    expose_headers=["X-Request-ID", "X-Correlation-ID"],
    allow_credentials=True,
)

app.include_router(health_router)
app.include_router(tools_router, prefix="/api")
app.include_router(agent_router, prefix="/api")
app.include_router(tasks_router, prefix="/api/tasks")
app.include_router(approvals_router, prefix="/api/approvals")
app.include_router(coding_router, prefix="/api")
app.include_router(agents_router, prefix="/api")
app.include_router(multi_agent_router, prefix="/api")
app.include_router(dashboard_router, prefix="/api")
app.include_router(system_router, prefix="/api")
app.include_router(learning_router, prefix="/api")
app.include_router(intelligence_router, prefix="/api")

# Phase 9: Mount stable API v1
from backend.app.api.routes.v1 import v1_router
app.include_router(v1_router)


@app.get("/health")
def liveness_check():
    """
    Liveness probe — verifies the process is alive and responsive.
    Does NOT check external dependencies. Used by Docker/K8s to decide
    whether to restart the container.
    """
    return {
        "status": "alive",
        "uptime_seconds": round(time.time() - _startup_time, 1),
        "version": "0.3.0",
    }


@app.get("/ready")
def readiness_check():
    """
    Readiness probe — verifies all critical subsystems are healthy before accepting traffic.
    Checks: database integrity, workspace directory, model router availability.
    Returns HTTP 503 if any subsystem is not ready.
    """
    checks: dict = {}
    all_ok = True

    # 1. Database health check
    try:
        from backend.app.services.database_health import DatabaseHealthService
        db_health = DatabaseHealthService.probe_health()
        checks["database"] = {
            "status": db_health.status,
            "latency_ms": db_health.latency_ms,
        }
        if db_health.status != "healthy":
            all_ok = False
    except Exception as exc:
        checks["database"] = {"status": "error", "error": str(exc)}
        all_ok = False

    # 2. Workspace directory check
    try:
        ws_path = getattr(settings, "WORKSPACE_BASE_DIR", None) or getattr(settings, "WORKSPACE_DIR", "workspace")
        import os
        ws_ok = os.path.isdir(ws_path)
        checks["workspace"] = {"status": "healthy" if ws_ok else "missing", "path": str(ws_path)}
        if not ws_ok:
            all_ok = False
    except Exception as exc:
        checks["workspace"] = {"status": "error", "error": str(exc)}
        all_ok = False

    # 3. Model router check
    try:
        from backend.app.services.model_router import ModelRouter
        router_summary = ModelRouter.get_runtime_summary()
        mr_status = router_summary.get("status", "unknown")
        checks["model_router"] = {"status": mr_status}
        if mr_status not in ("healthy", "degraded"):  # degraded still serves traffic
            all_ok = False
    except Exception as exc:
        checks["model_router"] = {"status": "error", "error": str(exc)}
        all_ok = False

    status_code = 200 if all_ok else 503
    return JSONResponse(
        status_code=status_code,
        content={
            "status": "ready" if all_ok else "not_ready",
            "checks": checks,
        },
    )


@app.get("/")
def read_root():
    return {"message": "AgentOS is running", "version": "0.3.0"}

