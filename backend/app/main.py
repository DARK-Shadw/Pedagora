import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.routers import health, agents, resources, teacher

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: eagerly load settings to fail fast on missing env vars
    get_settings()

    # Startup: reset ALL orphaned 'active' agent tasks. FastAPI BackgroundTasks
    # die with the process, so by definition any task still marked "active"
    # after a restart has no worker behind it. We previously had a 2h grace
    # window, but that meant restarting the server immediately after a task
    # started left it stuck "active" with no Retry button.
    try:
        from app.services.supabase import get_supabase
        sb = get_supabase()
        result = (
            sb.table("agent_tasks")
            .update({
                "status": "failed",
                "error_message": "Server restarted while task was running. Please retry.",
                "completed_at": datetime.now(timezone.utc).isoformat(),
            })
            .eq("status", "active")
            .execute()
        )
        if result.data:
            logger.warning(
                f"[Startup] Reset {len(result.data)} orphaned active task(s)"
            )
    except Exception as e:
        logger.error(f"[Startup] Orphan task cleanup failed: {e}")

    yield


app = FastAPI(
    title="Pedagora AI Backend",
    version="0.1.0",
    lifespan=lifespan,
)

settings = get_settings()

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_url],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(agents.router, prefix="/agents", tags=["agents"])
app.include_router(resources.router, prefix="/resources", tags=["resources"])
app.include_router(teacher.router, prefix="/teacher", tags=["teacher"])
