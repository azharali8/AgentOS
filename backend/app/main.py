from contextlib import asynccontextmanager
from fastapi import FastAPI
import logging

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
import backend.app.tools.test_runner  # trigger registration

logger = logging.getLogger(__name__)


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


@app.get("/ready")
def readiness_check():
    return {"status": "ready"}


@app.get("/")
def read_root():
    return {"message": "AgentOS is running", "version": "0.3.0"}
