from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.routers import health, agents, resources


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: eagerly load settings to fail fast on missing env vars
    get_settings()
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
