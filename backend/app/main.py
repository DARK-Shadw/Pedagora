import logging
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.routers import health, agents, resources, teacher

logger = logging.getLogger(__name__)

# Active agent_tasks older than this are considered orphaned (server died
# mid-pipeline) and will be reset to 'failed' on the next startup so users
# can retry them.
ORPHAN_TASK_CUTOFF_HOURS = 2


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: eagerly load settings to fail fast on missing env vars
    get_settings()

    # Startup: reset orphaned 'active' agent tasks left over from a crash
    try:
        from app.services.supabase import get_supabase
        sb = get_supabase()
        cutoff = (
            datetime.now(timezone.utc) - timedelta(hours=ORPHAN_TASK_CUTOFF_HOURS)
        ).isoformat()
        result = (
            sb.table("agent_tasks")
            .update({
                "status": "failed",
                "error_message": "Server restarted while task was running. Please retry.",
            })
            .eq("status", "active")
            .lt("started_at", cutoff)
            .execute()
        )
        if result.data:
            logger.warning(
                f"[Startup] Reset {len(result.data)} orphaned active task(s) "
                f"older than {ORPHAN_TASK_CUTOFF_HOURS}h"
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
