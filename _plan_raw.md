I cannot write to a plan file, so I will present the complete implementation plan directly in this response. I have now thoroughly explored every relevant file in the codebase. Here is the full design.

---

# Pedagora Research Agent Backend -- Complete Implementation Plan

## Table of Contents

1. [File Structure](#1-file-structure)
2. [SQL Migration: research_sources](#2-sql-migration)
3. [Environment Configuration](#3-environment-configuration)
4. [Pydantic Models](#4-pydantic-models)
5. [Supabase Service Layer](#5-supabase-service-layer)
6. [JWT Auth Middleware](#6-jwt-auth-middleware)
7. [Search Tool Implementations](#7-search-tool-implementations)
8. [3-Stage Pipeline Orchestration](#8-3-stage-pipeline-orchestration)
9. [System Prompts](#9-system-prompts)
10. [FastAPI Endpoint Design](#10-fastapi-endpoint-design)
11. [Frontend Integration (Trigger from Next.js)](#11-frontend-integration)
12. [Error Handling Strategy](#12-error-handling-strategy)
13. [Implementation Sequence](#13-implementation-sequence)

---

## 1. File Structure

```
backend/
├── .env.example
├── .env
├── .gitignore
├── requirements.txt
├── Dockerfile
├── render.yaml
├── README.md
│
├── app/
│   ├── __init__.py
│   ├── main.py                    # FastAPI app factory, CORS, lifespan
│   ├── config.py                  # Settings via pydantic-settings (env vars)
│   │
│   ├── auth/
│   │   ├── __init__.py
│   │   └── dependencies.py        # get_current_user JWT dependency
│   │
│   ├── models/
│   │   ├── __init__.py
│   │   ├── requests.py            # FastAPI request bodies
│   │   ├── responses.py           # FastAPI response bodies
│   │   ├── domain.py              # Internal domain models (TopicTree, SourceInfo, etc.)
│   │   └── database.py            # DB row shapes mirroring Supabase tables
│   │
│   ├── services/
│   │   ├── __init__.py
│   │   ├── supabase.py            # Supabase client singleton + helper methods
│   │   └── agent_task.py          # agent_tasks read/update helpers + log appender
│   │
│   ├── tools/
│   │   ├── __init__.py
│   │   ├── tavily.py              # Tavily search wrapper
│   │   ├── serper.py              # Serper Google Scholar wrapper
│   │   └── github.py              # GitHub API search wrapper
│   │
│   ├── agents/
│   │   ├── __init__.py
│   │   ├── prompts.py             # All system prompts for all 3 stages
│   │   ├── decompose.py           # Stage 1: DECOMPOSE agent (LLM only)
│   │   ├── research.py            # Stage 2: RESEARCH agent (ReAct with tools)
│   │   ├── synthesize.py          # Stage 3: SYNTHESIZE agent (LLM only)
│   │   └── pipeline.py            # Orchestrates all 3 stages in sequence
│   │
│   └── routers/
│       ├── __init__.py
│       ├── agents.py              # POST /agents/research, GET /agents/status/{goal_id}
│       └── health.py              # GET /health
│
└── tests/                         # Future: pytest tests
    ├── __init__.py
    ├── conftest.py
    ├── test_auth.py
    ├── test_tools.py
    └── test_pipeline.py
```

**Rationale**: The structure separates concerns cleanly: `auth/` for JWT verification, `models/` for all data shapes, `services/` for database access, `tools/` for external API wrappers, `agents/` for PydanticAI agent definitions and orchestration, `routers/` for FastAPI endpoints. This mirrors how the Next.js frontend is organized (types, lib, hooks, stores, app).

---

## 2. SQL Migration: `supabase/migrations/00004_add_research_sources.sql`

```sql
-- Research sources collected by the Research Agent
-- One row per source per goal

CREATE TABLE research_sources (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  goal_id UUID NOT NULL REFERENCES learning_goals(id) ON DELETE CASCADE,
  user_id UUID NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
  topic_group TEXT NOT NULL,                    -- which topic group this source belongs to
  source_type TEXT NOT NULL CHECK (source_type IN (
    'article', 'paper', 'repository', 'tutorial', 'video',
    'book', 'documentation', 'course', 'other'
  )),
  title TEXT NOT NULL,
  url TEXT,
  author TEXT,
  summary TEXT NOT NULL,                        -- AI-generated summary of why this source matters
  key_concepts TEXT[] NOT NULL DEFAULT '{}',    -- extracted concepts from this source
  relevance_score NUMERIC(3,2) NOT NULL DEFAULT 0.00 CHECK (relevance_score BETWEEN 0.00 AND 1.00),
  credibility_score NUMERIC(3,2) NOT NULL DEFAULT 0.00 CHECK (credibility_score BETWEEN 0.00 AND 1.00),
  content_extract TEXT,                         -- key passages or content pulled from the source
  metadata JSONB NOT NULL DEFAULT '{}',         -- flexible: stars, language, pub_date, citations, etc.
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Indexes
CREATE INDEX idx_research_sources_goal_id ON research_sources(goal_id);
CREATE INDEX idx_research_sources_user_id ON research_sources(user_id);

-- RLS
ALTER TABLE research_sources ENABLE ROW LEVEL SECURITY;

-- Users can view their own sources (for frontend display)
CREATE POLICY "Users can view own research sources"
  ON research_sources FOR SELECT USING (auth.uid() = user_id);

-- No user INSERT/UPDATE/DELETE policies — only service_role (backend) writes to this table

-- Also store the full research result (TopicTree + synthesis) as a JSONB document
CREATE TABLE research_results (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  goal_id UUID NOT NULL UNIQUE REFERENCES learning_goals(id) ON DELETE CASCADE,
  user_id UUID NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
  topic_tree JSONB NOT NULL,                    -- the full TopicTree from Stage 1
  synthesis JSONB NOT NULL,                     -- the final synthesis from Stage 3
  total_sources_found INTEGER NOT NULL DEFAULT 0,
  search_api_calls JSONB NOT NULL DEFAULT '{}', -- { tavily: 5, serper: 3, github: 2 }
  llm_tokens_used JSONB NOT NULL DEFAULT '{}',  -- { input: 12000, output: 3000 }
  duration_seconds NUMERIC(6,1) NOT NULL DEFAULT 0,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_research_results_goal_id ON research_results(goal_id);

ALTER TABLE research_results ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can view own research results"
  ON research_results FOR SELECT USING (auth.uid() = user_id);
```

**Why two tables**: `research_sources` stores individual normalized sources (one per row, queryable, filterable). `research_results` stores the full structured output document (topic tree + synthesis) as a single JSONB record per goal. This keeps downstream agents (Planning, Visualization) simple -- they just fetch one `research_results` row.

---

## 3. Environment Configuration

### `backend/.env.example`

```
# Supabase
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_SERVICE_ROLE_KEY=your-service-role-key
SUPABASE_JWT_SECRET=your-jwt-secret

# Google AI (Gemini)
GOOGLE_API_KEY=your-google-api-key

# Search APIs
TAVILY_API_KEY=your-tavily-api-key
SERPER_API_KEY=your-serper-api-key
GITHUB_TOKEN=your-github-personal-access-token

# App
ENVIRONMENT=development
FRONTEND_URL=http://localhost:3000
LOG_LEVEL=INFO
```

### `backend/app/config.py`

```python
from pydantic_settings import BaseSettings
from functools import lru_cache

class Settings(BaseSettings):
    # Supabase
    supabase_url: str
    supabase_service_role_key: str
    supabase_jwt_secret: str

    # Google AI
    google_api_key: str

    # Search APIs
    tavily_api_key: str
    serper_api_key: str = ""           # optional, has one-time credits
    github_token: str = ""             # optional, unauthenticated = 60 req/hr

    # App
    environment: str = "development"
    frontend_url: str = "http://localhost:3000"
    log_level: str = "INFO"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}

@lru_cache()
def get_settings() -> Settings:
    return Settings()
```

---

## 4. Pydantic Models

### `backend/app/models/domain.py` -- Internal domain models

```python
from pydantic import BaseModel, Field
from enum import Enum

# ============================================================
# Stage 1: DECOMPOSE output
# ============================================================

class TopicGroup(BaseModel):
    """A single topic group in the learning path."""
    order: int = Field(description="Sequence order, 1-based")
    title: str = Field(description="Topic group title, e.g. 'Linear Algebra Foundations'")
    description: str = Field(description="2-3 sentence description of what this covers")
    subtopics: list[str] = Field(description="3-7 specific subtopics within this group")
    prerequisites_from_tree: list[int] = Field(
        default_factory=list,
        description="Order numbers of topic groups that must be completed before this one"
    )
    estimated_importance: str = Field(
        description="'critical', 'important', or 'supplementary'"
    )
    search_queries: list[str] = Field(
        description="3-5 suggested search queries to research this topic"
    )

class TopicTree(BaseModel):
    """Stage 1 output: the decomposed topic structure."""
    goal_summary: str = Field(description="One-sentence restatement of the learning goal")
    total_topic_groups: int
    topic_groups: list[TopicGroup]
    prerequisite_gaps: list[str] = Field(
        default_factory=list,
        description="Skills the student is weak in that need attention"
    )
    estimated_total_hours: float = Field(
        description="Rough estimate of total learning hours"
    )

# ============================================================
# Stage 2: RESEARCH output (per topic group)
# ============================================================

class SourceType(str, Enum):
    ARTICLE = "article"
    PAPER = "paper"
    REPOSITORY = "repository"
    TUTORIAL = "tutorial"
    VIDEO = "video"
    BOOK = "book"
    DOCUMENTATION = "documentation"
    COURSE = "course"
    OTHER = "other"

class SourceInfo(BaseModel):
    """A single research source found for a topic group."""
    source_type: SourceType
    title: str
    url: str | None = None
    author: str | None = None
    summary: str = Field(description="Why this source matters for learning this topic")
    key_concepts: list[str] = Field(
        default_factory=list,
        description="Key concepts or topics covered by this source"
    )
    relevance_score: float = Field(ge=0.0, le=1.0, description="How relevant to the topic, 0-1")
    credibility_score: float = Field(ge=0.0, le=1.0, description="Source credibility, 0-1")
    content_extract: str | None = Field(
        default=None,
        description="Key passages or facts extracted from this source"
    )
    metadata: dict = Field(default_factory=dict)

class TopicResearchResult(BaseModel):
    """Research output for a single topic group."""
    topic_group_order: int
    topic_group_title: str
    sources: list[SourceInfo]
    coverage_notes: str = Field(
        description="What was well-covered vs. what had sparse results"
    )

# ============================================================
# Stage 3: SYNTHESIZE output
# ============================================================

class CrossReference(BaseModel):
    """A concept that appears across multiple topic groups."""
    concept: str
    appears_in: list[str] = Field(description="Topic group titles where this concept appears")
    significance: str

class GapAnalysis(BaseModel):
    """An identified gap in the research coverage."""
    topic_group: str
    gap_description: str
    severity: str = Field(description="'critical', 'moderate', or 'minor'")
    recommendation: str

class LearningPathRecommendation(BaseModel):
    """A recommendation for the course planner agent."""
    recommendation: str
    reasoning: str
    priority: str = Field(description="'high', 'medium', or 'low'")

class ResearchSynthesis(BaseModel):
    """Stage 3 output: the final synthesized research result."""
    executive_summary: str = Field(
        description="3-5 sentence summary of research findings for this learning goal"
    )
    total_sources_found: int
    strongest_topic_groups: list[str] = Field(
        description="Topic groups with the best research coverage"
    )
    weakest_topic_groups: list[str] = Field(
        description="Topic groups with sparse or low-quality sources"
    )
    cross_references: list[CrossReference]
    gaps: list[GapAnalysis]
    recommendations: list[LearningPathRecommendation]
    suggested_learning_order: list[str] = Field(
        description="Recommended order of topic groups based on research findings"
    )
```

### `backend/app/models/database.py` -- DB row shapes for Supabase reads

```python
from pydantic import BaseModel
from datetime import date, datetime

class LearningGoalRow(BaseModel):
    id: str
    user_id: str
    title: str
    end_goal: str | None
    motivation: str | None
    status: str
    is_exam_prep: bool
    exam_name: str | None
    exam_date: date | None

class ProfileRow(BaseModel):
    id: str
    education_level: str | None

class UserPreferencesRow(BaseModel):
    user_id: str
    learning_style: str
    content_depth: str
    teaching_style: str
    assessment_type: str
    learning_style_note: str
    content_depth_note: str
    teaching_style_note: str
    assessment_type_note: str
    education_level_note: str
    hours_per_week: int
    session_frequency: str

class PrerequisiteRow(BaseModel):
    skill_name: str
    confidence_level: str
    notes: str | None

class SkillAssessmentRow(BaseModel):
    question: str
    confidence_level: str

class AgentTaskRow(BaseModel):
    id: str
    goal_id: str
    user_id: str
    agent_type: str
    status: str
    progress_percentage: float
    current_task: str | None
    focus: str | None
    logs: list[dict]
    error_message: str | None
```

### `backend/app/models/requests.py`

```python
from pydantic import BaseModel

class TriggerResearchRequest(BaseModel):
    goal_id: str
```

### `backend/app/models/responses.py`

```python
from pydantic import BaseModel

class TriggerResearchResponse(BaseModel):
    status: str  # "accepted"
    goal_id: str
    message: str

class AgentStatusResponse(BaseModel):
    goal_id: str
    agent_type: str
    status: str
    progress_percentage: float
    current_task: str | None

class HealthResponse(BaseModel):
    status: str
    version: str
    environment: str
```

---

## 5. Supabase Service Layer

### `backend/app/services/supabase.py`

```python
from supabase import create_client, Client
from app.config import get_settings

_client: Client | None = None

def get_supabase() -> Client:
    """Singleton Supabase client using service_role key (bypasses RLS)."""
    global _client
    if _client is None:
        settings = get_settings()
        _client = create_client(settings.supabase_url, settings.supabase_service_role_key)
    return _client
```

### `backend/app/services/agent_task.py`

This is the critical file. It wraps all database operations for the `agent_tasks` table and provides the `log_and_update` method that the pipeline calls at every progress checkpoint.

```python
from datetime import datetime, timezone
from app.services.supabase import get_supabase

def _now_timestamp() -> str:
    """Returns HH:MM:SS in UTC for log entries."""
    return datetime.now(timezone.utc).strftime("%H:%M:%S")

async def fetch_onboarding_data(goal_id: str, user_id: str) -> dict:
    """
    Fetches all onboarding data needed by the research agent.
    Returns a dict with keys: goal, profile, preferences, prerequisites, skill_assessments.
    """
    sb = get_supabase()

    goal = sb.table("learning_goals").select("*").eq("id", goal_id).eq("user_id", user_id).single().execute()
    profile = sb.table("profiles").select("id, education_level").eq("id", user_id).single().execute()
    preferences = sb.table("user_preferences").select("*").eq("user_id", user_id).single().execute()
    prerequisites = sb.table("prerequisites").select("*").eq("goal_id", goal_id).eq("user_id", user_id).execute()
    skill_assessments = sb.table("skill_assessments").select("*").eq("goal_id", goal_id).eq("user_id", user_id).execute()

    return {
        "goal": goal.data,
        "profile": profile.data,
        "preferences": preferences.data,
        "prerequisites": prerequisites.data or [],
        "skill_assessments": skill_assessments.data or [],
    }

async def update_agent_task(
    goal_id: str,
    agent_type: str = "research",
    *,
    status: str | None = None,
    progress_percentage: float | None = None,
    current_task: str | None = None,
    focus: str | None = None,
    error_message: str | None = None,
    log_message: str | None = None,
    log_level: str = "info",
) -> None:
    """
    Update the agent_tasks row and optionally append a log entry.
    This is the single function that triggers Supabase Realtime updates to the frontend.
    """
    sb = get_supabase()

    # Build update payload -- only include non-None fields
    update_data: dict = {}
    if status is not None:
        update_data["status"] = status
    if progress_percentage is not None:
        update_data["progress_percentage"] = progress_percentage
    if current_task is not None:
        update_data["current_task"] = current_task
    if focus is not None:
        update_data["focus"] = focus
    if error_message is not None:
        update_data["error_message"] = error_message

    if status == "active":
        update_data["started_at"] = datetime.now(timezone.utc).isoformat()
    if status in ("completed", "failed"):
        update_data["completed_at"] = datetime.now(timezone.utc).isoformat()

    # Append log entry if provided
    if log_message:
        # Fetch existing logs first
        existing = (
            sb.table("agent_tasks")
            .select("logs")
            .eq("goal_id", goal_id)
            .eq("agent_type", agent_type)
            .single()
            .execute()
        )
        current_logs = existing.data.get("logs", []) if existing.data else []
        current_logs.append({
            "timestamp": _now_timestamp(),
            "agent": "RESEARCH_AGENT",
            "message": log_message,
            "level": log_level,
        })
        update_data["logs"] = current_logs

    if update_data:
        sb.table("agent_tasks").update(update_data).eq("goal_id", goal_id).eq("agent_type", agent_type).execute()

async def save_research_sources(
    goal_id: str,
    user_id: str,
    topic_group_title: str,
    sources: list[dict],
) -> None:
    """Insert research sources for a topic group into research_sources table."""
    sb = get_supabase()
    rows = []
    for s in sources:
        rows.append({
            "goal_id": goal_id,
            "user_id": user_id,
            "topic_group": topic_group_title,
            "source_type": s.get("source_type", "other"),
            "title": s.get("title", "Untitled"),
            "url": s.get("url"),
            "author": s.get("author"),
            "summary": s.get("summary", ""),
            "key_concepts": s.get("key_concepts", []),
            "relevance_score": s.get("relevance_score", 0.5),
            "credibility_score": s.get("credibility_score", 0.5),
            "content_extract": s.get("content_extract"),
            "metadata": s.get("metadata", {}),
        })
    if rows:
        sb.table("research_sources").insert(rows).execute()

async def save_research_result(
    goal_id: str,
    user_id: str,
    topic_tree: dict,
    synthesis: dict,
    total_sources: int,
    api_calls: dict,
    tokens_used: dict,
    duration_seconds: float,
) -> None:
    """Save the full research result document."""
    sb = get_supabase()
    sb.table("research_results").upsert({
        "goal_id": goal_id,
        "user_id": user_id,
        "topic_tree": topic_tree,
        "synthesis": synthesis,
        "total_sources_found": total_sources,
        "search_api_calls": api_calls,
        "llm_tokens_used": tokens_used,
        "duration_seconds": duration_seconds,
    }).execute()
```

**Key design decision**: `update_agent_task` is a single function that handles both field updates and log appending in one operation. The frontend's Supabase Realtime subscription listens for `UPDATE` events on `agent_tasks`, so every call to this function triggers a UI update. The log append uses a fetch-then-update pattern because Supabase does not support JSONB array append in a single update call from the Python client.

---

## 6. JWT Auth Middleware

### `backend/app/auth/dependencies.py`

```python
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import jwt, JWTError, ExpiredSignatureError
from app.config import get_settings

security = HTTPBearer()

async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> dict:
    """
    Verify Supabase JWT token and extract user info.
    
    Returns dict with keys: sub (user_id), email, role, aud, exp, etc.
    
    The JWT is signed with the Supabase JWT secret (HS256).
    Supabase tokens have audience="authenticated" for logged-in users.
    """
    settings = get_settings()
    token = credentials.credentials

    try:
        payload = jwt.decode(
            token,
            settings.supabase_jwt_secret,
            algorithms=["HS256"],
            audience="authenticated",
        )
        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token missing subject claim",
            )
        return payload

    except ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
        )
    except JWTError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid token: {str(e)}",
        )
```

**How the JWT reaches FastAPI**: The Next.js frontend obtains the access token from `supabase.auth.getSession()` and sends it as an `Authorization: Bearer <token>` header. The Supabase JWT secret is found in the Supabase project settings under "API" > "JWT Secret".

---

## 7. Search Tool Implementations

### `backend/app/tools/tavily.py`

```python
"""
Tavily Search wrapper.
Free tier: 1,000 credits/month (resets monthly).
Each search = 1 credit. Each extract = 1 credit.
"""
import logging
from tavily import AsyncTavilyClient
from app.config import get_settings

logger = logging.getLogger(__name__)

_client: AsyncTavilyClient | None = None

def _get_client() -> AsyncTavilyClient:
    global _client
    if _client is None:
        settings = get_settings()
        _client = AsyncTavilyClient(api_key=settings.tavily_api_key)
    return _client

async def tavily_search(query: str, max_results: int = 5) -> list[dict]:
    """
    Search the web via Tavily. Returns AI-scored, LLM-ready results.
    
    Each result has: title, url, content (extracted text), score (relevance).
    """
    try:
        client = _get_client()
        response = await client.search(
            query=query,
            max_results=max_results,
            search_depth="basic",        # "basic" = 1 credit, "advanced" = 2 credits
            include_answer=False,        # save tokens, we do our own synthesis
            include_raw_content=False,   # save bandwidth
        )
        results = []
        for r in response.get("results", []):
            results.append({
                "title": r.get("title", ""),
                "url": r.get("url", ""),
                "content": r.get("content", ""),
                "score": r.get("score", 0.0),
            })
        return results
    except Exception as e:
        logger.error(f"Tavily search failed for '{query}': {e}")
        return []
```

### `backend/app/tools/serper.py`

```python
"""
Serper.dev Google Scholar wrapper.
Free tier: 2,500 queries (one-time, no expiry).
Best for: academic papers, scholarly content.
"""
import logging
import httpx
from app.config import get_settings

logger = logging.getLogger(__name__)

SERPER_SCHOLAR_URL = "https://google.serper.dev/scholar"

async def serper_scholar_search(query: str, num_results: int = 5) -> list[dict]:
    """
    Search Google Scholar via Serper. Returns academic paper results.
    
    Each result has: title, link, snippet, publication_info, cited_by count.
    """
    settings = get_settings()
    if not settings.serper_api_key:
        logger.warning("Serper API key not configured, skipping scholar search")
        return []

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                SERPER_SCHOLAR_URL,
                json={"q": query, "num": num_results},
                headers={
                    "X-API-KEY": settings.serper_api_key,
                    "Content-Type": "application/json",
                },
            )
            response.raise_for_status()
            data = response.json()

        results = []
        for r in data.get("organic", []):
            results.append({
                "title": r.get("title", ""),
                "url": r.get("link", ""),
                "snippet": r.get("snippet", ""),
                "publication_info": r.get("publicationInfo", {}).get("summary", ""),
                "cited_by": r.get("citedBy", {}).get("total", 0),
            })
        return results
    except Exception as e:
        logger.error(f"Serper scholar search failed for '{query}': {e}")
        return []
```

### `backend/app/tools/github.py`

```python
"""
GitHub API search wrapper.
Free tier: 5,000 requests/hour with token, 60/hour without.
Search endpoint: 30 requests/minute (separate limit).
"""
import logging
import httpx
from app.config import get_settings

logger = logging.getLogger(__name__)

GITHUB_SEARCH_URL = "https://api.github.com/search/repositories"

async def github_search(query: str, max_results: int = 5) -> list[dict]:
    """
    Search GitHub repos by topic. Returns top repos sorted by stars.
    
    Each result has: name, full_name, url, description, stars, language, topics, updated_at.
    """
    settings = get_settings()
    headers = {"Accept": "application/vnd.github.v3+json"}
    if settings.github_token:
        headers["Authorization"] = f"token {settings.github_token}"

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                GITHUB_SEARCH_URL,
                params={
                    "q": query,
                    "sort": "stars",
                    "order": "desc",
                    "per_page": max_results,
                },
                headers=headers,
            )
            response.raise_for_status()
            data = response.json()

        results = []
        for repo in data.get("items", []):
            results.append({
                "name": repo.get("name", ""),
                "full_name": repo.get("full_name", ""),
                "url": repo.get("html_url", ""),
                "description": repo.get("description", ""),
                "stars": repo.get("stargazers_count", 0),
                "language": repo.get("language", ""),
                "topics": repo.get("topics", []),
                "updated_at": repo.get("updated_at", ""),
            })
        return results
    except Exception as e:
        logger.error(f"GitHub search failed for '{query}': {e}")
        return []
```

---

## 8. 3-Stage Pipeline Orchestration

### `backend/app/agents/decompose.py` -- Stage 1

```python
"""
Stage 1: DECOMPOSE
LLM-only call. Takes onboarding data, returns TopicTree.
No tools. Single structured output call. ~2-3 seconds.
"""
from pydantic_ai import Agent
from app.models.domain import TopicTree
from app.agents.prompts import get_decompose_prompt

decompose_agent = Agent(
    "google-gla:gemini-2.5-flash",
    output_type=TopicTree,
    system_prompt=get_decompose_prompt(),
)

async def run_decompose(onboarding_context: str) -> TopicTree:
    """
    Run the decompose agent to generate the topic tree.
    
    Args:
        onboarding_context: A formatted string with all onboarding data.
    
    Returns:
        TopicTree: structured decomposition of the learning goal.
    """
    result = await decompose_agent.run(onboarding_context)
    return result.output
```

### `backend/app/agents/research.py` -- Stage 2

```python
"""
Stage 2: RESEARCH
ReAct agent with tools. Runs once per topic group.
Tools: tavily_search, serper_scholar, github_search.
Each run outputs list[SourceInfo] for that topic.
"""
from dataclasses import dataclass
from pydantic_ai import Agent, RunContext
from pydantic_ai.settings import UsageLimits
from app.models.domain import TopicResearchResult
from app.tools.tavily import tavily_search
from app.tools.serper import serper_scholar_search
from app.tools.github import github_search
from app.agents.prompts import get_research_prompt

@dataclass
class ResearchDeps:
    """Dependencies injected into each research agent run."""
    topic_order: int
    topic_title: str
    topic_description: str
    subtopics: list[str]
    search_queries: list[str]
    education_level: str
    goal_title: str
    content_depth: str

research_agent = Agent(
    "google-gla:gemini-2.5-flash",
    deps_type=ResearchDeps,
    output_type=TopicResearchResult,
    system_prompt=get_research_prompt(),
)

@research_agent.tool
async def web_search(ctx: RunContext[ResearchDeps], query: str) -> str:
    """Search the web for educational resources, articles, and tutorials."""
    results = await tavily_search(query, max_results=5)
    if not results:
        return "No results found."
    formatted = []
    for r in results:
        formatted.append(
            f"Title: {r['title']}\n"
            f"URL: {r['url']}\n"
            f"Relevance: {r['score']:.2f}\n"
            f"Content: {r['content'][:500]}\n"
        )
    return "\n---\n".join(formatted)

@research_agent.tool
async def scholar_search(ctx: RunContext[ResearchDeps], query: str) -> str:
    """Search Google Scholar for academic papers and research publications."""
    results = await serper_scholar_search(query, num_results=5)
    if not results:
        return "No academic results found."
    formatted = []
    for r in results:
        formatted.append(
            f"Title: {r['title']}\n"
            f"URL: {r['url']}\n"
            f"Snippet: {r['snippet']}\n"
            f"Publication: {r['publication_info']}\n"
            f"Citations: {r['cited_by']}\n"
        )
    return "\n---\n".join(formatted)

@research_agent.tool
async def code_search(ctx: RunContext[ResearchDeps], query: str) -> str:
    """Search GitHub for repositories with working code examples and implementations."""
    results = await github_search(query, max_results=5)
    if not results:
        return "No repositories found."
    formatted = []
    for r in results:
        formatted.append(
            f"Repo: {r['full_name']}\n"
            f"URL: {r['url']}\n"
            f"Stars: {r['stars']}\n"
            f"Language: {r['language']}\n"
            f"Description: {r['description']}\n"
            f"Topics: {', '.join(r['topics'])}\n"
        )
    return "\n---\n".join(formatted)

async def run_research_for_topic(
    topic_order: int,
    topic_title: str,
    topic_description: str,
    subtopics: list[str],
    search_queries: list[str],
    education_level: str,
    goal_title: str,
    content_depth: str,
) -> TopicResearchResult:
    """
    Run the research agent for a single topic group.
    
    Returns TopicResearchResult with sources and coverage notes.
    """
    deps = ResearchDeps(
        topic_order=topic_order,
        topic_title=topic_title,
        topic_description=topic_description,
        subtopics=subtopics,
        search_queries=search_queries,
        education_level=education_level,
        goal_title=goal_title,
        content_depth=content_depth,
    )

    prompt = (
        f"Research the topic group: '{topic_title}'\n"
        f"Description: {topic_description}\n"
        f"Subtopics to cover: {', '.join(subtopics)}\n"
        f"Suggested search queries: {', '.join(search_queries)}\n"
        f"Education level: {education_level}\n"
        f"Content depth: {content_depth}\n"
        f"Overall learning goal: {goal_title}\n\n"
        f"Use the available search tools to find high-quality sources for this topic. "
        f"Search for foundational resources, practical examples, and academic papers if appropriate. "
        f"Aim for 3-8 diverse, high-quality sources."
    )

    result = await research_agent.run(
        prompt,
        deps=deps,
        usage_limits=UsageLimits(
            request_limit=10,        # max 10 LLM round-trips per topic
            response_tokens_limit=4000,
        ),
    )
    return result.output
```

### `backend/app/agents/synthesize.py` -- Stage 3

```python
"""
Stage 3: SYNTHESIZE
LLM-only call. Takes TopicTree + all collected sources, outputs ResearchSynthesis.
No tools. Single structured output call. ~3-5 seconds.
"""
from pydantic_ai import Agent
from app.models.domain import ResearchSynthesis
from app.agents.prompts import get_synthesize_prompt

synthesize_agent = Agent(
    "google-gla:gemini-2.5-flash",
    output_type=ResearchSynthesis,
    system_prompt=get_synthesize_prompt(),
)

async def run_synthesize(
    topic_tree_json: str,
    all_sources_json: str,
    goal_title: str,
    education_level: str,
) -> ResearchSynthesis:
    """
    Run the synthesize agent to produce the final research result.
    """
    prompt = (
        f"## Learning Goal\n{goal_title}\n\n"
        f"## Student Education Level\n{education_level}\n\n"
        f"## Topic Tree\n{topic_tree_json}\n\n"
        f"## All Collected Sources\n{all_sources_json}\n\n"
        f"Synthesize all research findings into a comprehensive analysis."
    )

    result = await synthesize_agent.run(prompt)
    return result.output
```

### `backend/app/agents/pipeline.py` -- The Orchestrator

This is the most critical file. It runs all 3 stages in sequence, updating `agent_tasks` at every checkpoint so the frontend shows live progress.

```python
"""
Research pipeline orchestrator.
Runs: DECOMPOSE → RESEARCH (per topic) → SYNTHESIZE
Updates agent_tasks at every checkpoint for real-time frontend updates.
"""
import json
import time
import logging
from app.agents.decompose import run_decompose
from app.agents.research import run_research_for_topic
from app.agents.synthesize import run_synthesize
from app.services.agent_task import (
    fetch_onboarding_data,
    update_agent_task,
    save_research_sources,
    save_research_result,
)

logger = logging.getLogger(__name__)

def _build_onboarding_context(data: dict) -> str:
    """Format all onboarding data into a single string for Stage 1."""
    goal = data["goal"]
    profile = data["profile"]
    prefs = data["preferences"]
    prereqs = data["prerequisites"]
    assessments = data["skill_assessments"]

    prereq_lines = []
    for p in prereqs:
        prereq_lines.append(
            f"  - {p['skill_name']} (confidence: {p['confidence_level']})"
            + (f" — note: {p['notes']}" if p.get("notes") else "")
        )

    assessment_lines = []
    for a in assessments:
        assessment_lines.append(
            f"  - Q: {a['question']} → confidence: {a['confidence_level']}"
        )

    context = f"""## Learning Goal
Title: {goal['title']}
End Goal: {goal.get('end_goal') or 'Not specified'}
Motivation: {goal.get('motivation') or 'Not specified'}
Is Exam Prep: {goal.get('is_exam_prep', False)}
{f"Exam: {goal.get('exam_name')} on {goal.get('exam_date')}" if goal.get('is_exam_prep') else ''}

## Student Profile
Education Level: {profile.get('education_level') or 'Not specified'}

## Learning Preferences
Learning Style: {prefs.get('learning_style', 'balanced')}
{f"Note: {prefs.get('learning_style_note')}" if prefs.get('learning_style_note') else ''}
Content Depth: {prefs.get('content_depth', 'intermediate')}
{f"Note: {prefs.get('content_depth_note')}" if prefs.get('content_depth_note') else ''}
Teaching Style: {prefs.get('teaching_style', 'socratic')}
{f"Note: {prefs.get('teaching_style_note')}" if prefs.get('teaching_style_note') else ''}
Hours Per Week: {prefs.get('hours_per_week', 5)}

## Prerequisites (Student Self-Reported)
{chr(10).join(prereq_lines) if prereq_lines else '  None specified'}

## Skill Assessment Results
{chr(10).join(assessment_lines) if assessment_lines else '  No assessment taken'}
"""
    return context.strip()


async def run_research_pipeline(goal_id: str, user_id: str) -> None:
    """
    Main pipeline entry point. Called as a background task.
    
    Stages:
      1. DECOMPOSE — generate TopicTree from onboarding data
      2. RESEARCH — for each topic group, run ReAct agent with search tools
      3. SYNTHESIZE — produce final analysis from all sources
    
    Updates agent_tasks row at every checkpoint for real-time UI feedback.
    """
    pipeline_start = time.time()
    api_call_counts = {"tavily": 0, "serper": 0, "github": 0}
    total_sources = 0

    try:
        # ============================================================
        # ACTIVATE — mark agent as active
        # ============================================================
        await update_agent_task(
            goal_id,
            status="active",
            progress_percentage=0,
            current_task="Initializing research pipeline...",
            focus="Initialization",
            log_message="Research agent activated. Beginning analysis.",
            log_level="system",
        )

        # ============================================================
        # FETCH onboarding data
        # ============================================================
        await update_agent_task(
            goal_id,
            progress_percentage=2,
            current_task="Loading learning profile...",
            log_message="Fetching onboarding data from database.",
        )
        onboarding_data = await fetch_onboarding_data(goal_id, user_id)

        if not onboarding_data.get("goal"):
            raise ValueError(f"No learning goal found for goal_id={goal_id}")

        context = _build_onboarding_context(onboarding_data)
        education_level = onboarding_data["profile"].get("education_level") or "self_learner"
        content_depth = onboarding_data["preferences"].get("content_depth") or "intermediate"
        goal_title = onboarding_data["goal"]["title"]

        # ============================================================
        # STAGE 1: DECOMPOSE
        # ============================================================
        await update_agent_task(
            goal_id,
            progress_percentage=5,
            current_task="Decomposing learning goal into topic groups...",
            focus="Topic Decomposition",
            log_message=f"Stage 1/3: Decomposing '{goal_title}' into topic groups.",
        )

        topic_tree = await run_decompose(context)

        num_topics = len(topic_tree.topic_groups)
        await update_agent_task(
            goal_id,
            progress_percentage=10,
            current_task=f"Identified {num_topics} topic groups to research.",
            log_message=f"Decomposition complete: {num_topics} topic groups identified.",
            log_level="success",
        )

        # ============================================================
        # STAGE 2: RESEARCH (per topic group)
        # ============================================================
        # Progress from 10% to 85%, divided evenly across topic groups.
        progress_per_topic = 75.0 / max(num_topics, 1)
        all_topic_results = []

        for i, topic_group in enumerate(topic_tree.topic_groups):
            topic_progress_base = 10.0 + (i * progress_per_topic)
            topic_number = i + 1

            await update_agent_task(
                goal_id,
                progress_percentage=round(topic_progress_base, 1),
                current_task=f"Researching {topic_number}/{num_topics}: {topic_group.title}",
                focus=topic_group.title,
                log_message=f"Stage 2/3: Researching topic {topic_number}/{num_topics} — {topic_group.title}.",
            )

            try:
                topic_result = await run_research_for_topic(
                    topic_order=topic_group.order,
                    topic_title=topic_group.title,
                    topic_description=topic_group.description,
                    subtopics=topic_group.subtopics,
                    search_queries=topic_group.search_queries,
                    education_level=education_level,
                    goal_title=goal_title,
                    content_depth=content_depth,
                )

                # Save sources to DB immediately after each topic
                sources_dicts = [s.model_dump() for s in topic_result.sources]
                await save_research_sources(
                    goal_id, user_id, topic_group.title, sources_dicts
                )

                topic_source_count = len(topic_result.sources)
                total_sources += topic_source_count
                all_topic_results.append(topic_result)

                await update_agent_task(
                    goal_id,
                    progress_percentage=round(topic_progress_base + progress_per_topic, 1),
                    current_task=f"Found {topic_source_count} sources for {topic_group.title}.",
                    log_message=f"Topic '{topic_group.title}': {topic_source_count} sources collected.",
                    log_level="success",
                )

            except Exception as topic_err:
                # If one topic fails, log the error and continue with others
                logger.error(f"Research failed for topic '{topic_group.title}': {topic_err}")
                all_topic_results.append(None)  # placeholder

                await update_agent_task(
                    goal_id,
                    progress_percentage=round(topic_progress_base + progress_per_topic, 1),
                    current_task=f"Partial failure on {topic_group.title}, continuing...",
                    log_message=f"Warning: Research for '{topic_group.title}' failed: {str(topic_err)[:100]}. Continuing with remaining topics.",
                    log_level="error",
                )

        # ============================================================
        # STAGE 3: SYNTHESIZE
        # ============================================================
        await update_agent_task(
            goal_id,
            progress_percentage=87,
            current_task="Synthesizing research findings...",
            focus="Synthesis",
            log_message=f"Stage 3/3: Synthesizing {total_sources} sources across {num_topics} topic groups.",
        )

        # Build input for synthesis
        collected_sources = []
        for tr in all_topic_results:
            if tr is not None:
                collected_sources.append(tr.model_dump())

        synthesis = await run_synthesize(
            topic_tree_json=topic_tree.model_dump_json(indent=2),
            all_sources_json=json.dumps(collected_sources, indent=2, default=str),
            goal_title=goal_title,
            education_level=education_level,
        )

        # ============================================================
        # SAVE FINAL RESULT
        # ============================================================
        await update_agent_task(
            goal_id,
            progress_percentage=95,
            current_task="Saving research results...",
            log_message="Persisting final research results to database.",
        )

        duration = round(time.time() - pipeline_start, 1)
        await save_research_result(
            goal_id=goal_id,
            user_id=user_id,
            topic_tree=topic_tree.model_dump(),
            synthesis=synthesis.model_dump(),
            total_sources=total_sources,
            api_calls=api_call_counts,
            tokens_used={},  # PydanticAI exposes usage on result, aggregate here
            duration_seconds=duration,
        )

        # ============================================================
        # COMPLETE
        # ============================================================
        await update_agent_task(
            goal_id,
            status="completed",
            progress_percentage=100,
            current_task="Research complete",
            focus="Complete",
            log_message=f"Research pipeline completed in {duration}s. {total_sources} sources across {num_topics} topics.",
            log_level="success",
        )

    except Exception as e:
        logger.exception(f"Research pipeline failed for goal_id={goal_id}")
        duration = round(time.time() - pipeline_start, 1)
        await update_agent_task(
            goal_id,
            status="failed",
            error_message=str(e)[:500],
            current_task="Research failed",
            log_message=f"Pipeline failed after {duration}s: {str(e)[:200]}",
            log_level="error",
        )
```

---

## 9. System Prompts

### `backend/app/agents/prompts.py`

```python
"""
All system prompts for the research pipeline stages.
Kept in a single file for easy iteration and A/B testing.
"""


def get_decompose_prompt() -> str:
    return """You are a Topic Decomposition Agent for Pedagora, an AI education platform.

Your job is to take a student's learning goal and break it down into a structured, ordered list of topic groups that form a complete learning path.

## What You Receive
You will receive the student's complete learning profile:
- Their learning goal (title, end goal, motivation)
- Education level
- Learning preferences (style, depth, teaching method)
- Self-reported prerequisites and confidence levels
- Skill assessment results

## What You Must Output
A TopicTree with 5-10 topic groups. Each topic group represents a major section of study.

## Rules
1. ORDER topic groups from foundational to advanced. Prerequisites come first.
2. If the student has prerequisite gaps (low confidence in foundational skills), include review/remediation topic groups FIRST.
3. Each topic group should have 3-7 specific subtopics.
4. Mark prerequisite dependencies between topic groups using the `prerequisites_from_tree` field.
5. Generate 3-5 search queries per topic group that would find HIGH-QUALITY educational resources. Include:
   - A query targeting official documentation or textbooks
   - A query targeting practical tutorials or examples
   - A query targeting academic papers (if the content depth warrants it)
   - A query targeting code repositories (if the topic involves programming)
6. Rate each topic group's importance: 'critical' (must learn), 'important' (should learn), 'supplementary' (nice to have).
7. Estimate total learning hours based on the content depth and number of topics.
8. Adapt topic granularity to the student's education level:
   - High school / beginner: fewer, broader topic groups with more review
   - Graduate / professional: more specific, deeper topic groups
9. If it's exam prep, include topic groups specifically for exam patterns and practice.
10. Keep topic group titles clear, descriptive, and specific — not vague like "Introduction" or "Advanced Topics".

## Quality Criteria
- A good decomposition lets someone go from zero to the end goal by studying the topics in order.
- Each topic group should be researchable (the search queries should yield real results).
- The total should feel achievable within the student's available hours per week."""


def get_research_prompt() -> str:
    return """You are a Research Agent for Pedagora, an AI education platform.

Your job is to research ONE topic group thoroughly and gather HIGH-QUALITY, REAL sources that a teaching AI can later use to create accurate lessons.

## Your Tools
You have 3 search tools:
1. `web_search(query)` — General web search via Tavily. Best for tutorials, articles, documentation. Returns relevance-scored results.
2. `scholar_search(query)` — Google Scholar via Serper. Best for academic papers, research publications. Returns citation counts.
3. `code_search(query)` — GitHub repository search. Best for working code examples, implementations. Returns stars and descriptions.

## Your Research Process
1. Start with the suggested search queries provided in the topic description.
2. Based on initial results, formulate follow-up queries to fill gaps.
3. For each source found, assess:
   - Relevance: How directly does this teach the subtopics? (0.0-1.0)
   - Credibility: Is this a reputable source? (0.0-1.0)
     - Official docs, textbooks, highly-cited papers: 0.8-1.0
     - University courses, well-known tech blogs: 0.6-0.8
     - Random blog posts, uncited content: 0.3-0.5
4. Extract key concepts and a brief content summary from each source.
5. Aim for 3-8 diverse sources per topic group. Quality over quantity.

## Rules
- ONLY include sources you've actually found via the search tools.
- NEVER fabricate URLs, titles, authors, or content.
- Prefer sources that match the student's education level and content depth.
- Prioritize: official docs > textbooks > university courses > quality tutorials > blog posts.
- For programming topics: prefer repos with >50 stars, recent commits, good READMEs.
- If a search returns no results, try alternative queries before giving up.
- Be efficient with tool calls — you have a limited number of round-trips.
- Set source_type accurately: article, paper, repository, tutorial, video, book, documentation, course, other.

## Coverage Notes
After researching, honestly assess what was well-covered vs. what had sparse results.
This helps the synthesis stage identify gaps."""


def get_synthesize_prompt() -> str:
    return """You are a Research Synthesis Agent for Pedagora, an AI education platform.

Your job is to take all research findings (topic tree + sources collected across all topic groups) and produce a comprehensive synthesis that will guide the Course Planner Agent.

## What You Receive
1. The TopicTree — the decomposed topic structure
2. All collected sources — organized by topic group, with relevance and credibility scores

## What You Must Produce
A ResearchSynthesis with:

1. **Executive Summary** (3-5 sentences): What was researched, key findings, overall quality of available resources.

2. **Strongest/Weakest Topic Groups**: Which topics had excellent research coverage? Which were sparse?

3. **Cross-References**: Concepts that appear across multiple topic groups. These are KEY connections that the course planner should emphasize.

4. **Gap Analysis**: Where is the research coverage insufficient? What topics need supplementation?
   - severity: 'critical' (cannot teach without more info), 'moderate' (can teach but may lack depth), 'minor' (supplementary content missing)
   - recommendation: what the course planner should do about it

5. **Learning Path Recommendations**: Strategic advice for the Course Planner Agent:
   - Should certain topic groups be merged or split?
   - Are there topics that need more practical examples vs theory?
   - Does the research suggest a different ordering than the original TopicTree?
   - Are there emergent topics that should be added?

6. **Suggested Learning Order**: Based on what you now know from the research, what's the optimal order?

## Rules
- Base ALL conclusions on actual source data. Do not invent findings.
- Be specific in cross-references — name the exact concepts and which topic groups share them.
- Gap analysis should be actionable — tell the planner exactly what's missing.
- Recommendations should account for the student's education level.
- If research coverage was excellent for a topic, say so. If it was poor, be honest.
- The synthesis should help the Course Planner Agent create a better curriculum than the original TopicTree alone would suggest."""
```

---

## 10. FastAPI Endpoint Design

### `backend/app/main.py`

```python
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.config import get_settings
from app.routers import agents, health

logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup/shutdown events."""
    settings = get_settings()
    logging.basicConfig(level=getattr(logging, settings.log_level))
    logger.info(f"Starting Pedagora Backend ({settings.environment})")
    yield
    logger.info("Shutting down Pedagora Backend")

app = FastAPI(
    title="Pedagora Backend",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS — allow Next.js frontend
settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_url, "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(agents.router, prefix="/agents", tags=["agents"])
```

### `backend/app/routers/health.py`

```python
from fastapi import APIRouter
from app.config import get_settings
from app.models.responses import HealthResponse

router = APIRouter()

@router.get("/health", response_model=HealthResponse)
async def health_check():
    settings = get_settings()
    return HealthResponse(
        status="ok",
        version="0.1.0",
        environment=settings.environment,
    )
```

### `backend/app/routers/agents.py`

```python
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from app.auth.dependencies import get_current_user
from app.models.requests import TriggerResearchRequest
from app.models.responses import TriggerResearchResponse, AgentStatusResponse
from app.agents.pipeline import run_research_pipeline
from app.services.supabase import get_supabase

router = APIRouter()

@router.post("/research", response_model=TriggerResearchResponse, status_code=202)
async def trigger_research(
    request: TriggerResearchRequest,
    background_tasks: BackgroundTasks,
    user: dict = Depends(get_current_user),
):
    """
    Trigger the research agent pipeline for a learning goal.
    
    Returns immediately with 202 Accepted. The pipeline runs as a background task
    and updates agent_tasks via Supabase (which pushes to frontend via Realtime).
    """
    user_id = user["sub"]
    goal_id = request.goal_id

    # Verify the goal exists and belongs to this user
    sb = get_supabase()
    goal_check = (
        sb.table("learning_goals")
        .select("id, user_id")
        .eq("id", goal_id)
        .eq("user_id", user_id)
        .single()
        .execute()
    )
    if not goal_check.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Learning goal not found or does not belong to you",
        )

    # Verify the research task exists and is in 'queued' status
    task_check = (
        sb.table("agent_tasks")
        .select("id, status")
        .eq("goal_id", goal_id)
        .eq("agent_type", "research")
        .single()
        .execute()
    )
    if not task_check.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No research agent task found for this goal",
        )
    if task_check.data["status"] not in ("queued", "failed"):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Research task is already {task_check.data['status']}",
        )

    # Launch pipeline as background task
    background_tasks.add_task(run_research_pipeline, goal_id, user_id)

    return TriggerResearchResponse(
        status="accepted",
        goal_id=goal_id,
        message="Research pipeline started. Watch agent_tasks for real-time updates.",
    )

@router.get("/status/{goal_id}", response_model=list[AgentStatusResponse])
async def get_agent_status(
    goal_id: str,
    user: dict = Depends(get_current_user),
):
    """
    Get current status of all agent tasks for a goal.
    This is a fallback for when Realtime isn't connected.
    """
    user_id = user["sub"]
    sb = get_supabase()
    result = (
        sb.table("agent_tasks")
        .select("goal_id, agent_type, status, progress_percentage, current_task")
        .eq("goal_id", goal_id)
        .eq("user_id", user_id)
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="No agent tasks found")

    return [
        AgentStatusResponse(
            goal_id=t["goal_id"],
            agent_type=t["agent_type"],
            status=t["status"],
            progress_percentage=t["progress_percentage"],
            current_task=t.get("current_task"),
        )
        for t in result.data
    ]
```

**Key design decision: `BackgroundTasks`**: FastAPI's built-in `BackgroundTasks` is used instead of Celery or a separate task queue. This is appropriate because:
1. Render's free tier runs a single web process (no separate worker needed)
2. The pipeline runs for 30-90 seconds, well within HTTP connection limits
3. The response returns immediately with 202 Accepted
4. Progress is communicated via Supabase Realtime, not HTTP polling

If the app scales beyond a single process, replace `BackgroundTasks` with a proper task queue (e.g., Supabase Edge Functions trigger, or a Redis-based queue).

---

## 11. Frontend Integration (Trigger from Next.js)

The trigger point is in the review page at `C:\Programming\MyProjects\Pedagora\src\app\(onboarding)\onboarding\review\page.tsx`. Currently, after step 6 (creating agent tasks), the code redirects to `/agents`. The research trigger should fire between step 6 and step 7.

### Changes needed in `review/page.tsx`

After line 128 (agent tasks insert), add a call to trigger the backend:

```typescript
// 6.5 Trigger research agent on the backend
const { data: sessionData } = await supabase.auth.getSession();
const accessToken = sessionData?.session?.access_token;

if (accessToken) {
    // Fire-and-forget — don't await, don't block onboarding completion
    fetch(`${process.env.NEXT_PUBLIC_BACKEND_URL}/agents/research`, {
        method: "POST",
        headers: {
            "Content-Type": "application/json",
            "Authorization": `Bearer ${accessToken}`,
        },
        body: JSON.stringify({ goal_id: goalData.id }),
    }).catch((err) => {
        // Log but don't fail onboarding — research can be retriggered
        console.error("Failed to trigger research agent:", err);
    });
}
```

### New env var needed in `.env.local`

```
NEXT_PUBLIC_BACKEND_URL=http://localhost:8000
```

**Why fire-and-forget**: The backend returns 202 Accepted immediately. The actual research pipeline runs as a background task. The user is already on the `/agents` page watching Realtime updates by the time the pipeline starts. Blocking the onboarding completion on a backend call would be bad UX (especially with Render cold starts of ~30 seconds).

### Alternative approach: API route proxy

If CORS becomes an issue or you want to hide the backend URL from the client, create a Next.js API route:

```
src/app/api/agents/research/route.ts
```

This route would:
1. Verify the user via Supabase server client
2. Fetch the access token
3. Forward the request to the FastAPI backend
4. Return the response

This is optional -- direct calls with CORS are simpler for an MVP.

### Retry mechanism on the agents page

Add a "Retry" button on the agents page for when research fails. This calls the same `POST /agents/research` endpoint. The backend already checks that the task is in `queued` or `failed` status before accepting.

---

## 12. Error Handling Strategy

### 12.1 Per-Topic Resilience

In `pipeline.py`, each topic group's research is wrapped in its own try/except. If topic 3 of 8 fails, topics 4-8 still run. The failure is logged with level "error" and the frontend shows the error in the log viewer.

### 12.2 Search API Failures

Each tool in `backend/app/tools/` catches all exceptions and returns an empty list `[]` instead of raising. The research agent sees "No results found" and either tries a different query or moves on. This means a Tavily outage does not crash the pipeline.

### 12.3 LLM Failures

PydanticAI handles retries internally when the model returns output that does not match the expected Pydantic schema (via `ModelRetry`). The `UsageLimits` configuration prevents infinite retry loops by capping total requests per topic.

### 12.4 Pipeline-Level Failure

If the entire pipeline crashes (e.g., database connection lost), the outer try/except in `run_research_pipeline` catches it, marks the agent_task as `failed` with an error message, and logs the failure. The frontend shows the "FAILED" status.

### 12.5 Idempotency and Retries

The `POST /agents/research` endpoint checks that the task is in `queued` or `failed` status before accepting. If it is `failed`, the pipeline can be re-triggered. Before re-running, the pipeline should delete any existing `research_sources` for that goal (to avoid duplicates). Add this to the start of `run_research_pipeline`:

```python
# Clean up any partial results from a previous failed run
sb = get_supabase()
sb.table("research_sources").delete().eq("goal_id", goal_id).execute()
sb.table("research_results").delete().eq("goal_id", goal_id).execute()
```

### 12.6 Rate Limit Awareness

The tools should track API call counts. If Tavily returns a 429 (rate limited), fall back to formulating the answer from already-collected sources. The `api_call_counts` dict in the pipeline tracks usage for cost monitoring.

---

## 13. Implementation Sequence

### Step 1: Foundation (Day 1)
1. Create `backend/` directory structure
2. Create `requirements.txt`, `.env.example`, `.gitignore`
3. Implement `app/config.py` (settings)
4. Implement `app/main.py` (FastAPI app with CORS)
5. Implement `app/routers/health.py` (health check)
6. Test: `uvicorn app.main:app --reload` and hit `/health`

### Step 2: Auth + DB (Day 1-2)
7. Implement `app/auth/dependencies.py` (JWT verification)
8. Implement `app/services/supabase.py` (client singleton)
9. Run the `00004_add_research_sources.sql` migration in Supabase SQL editor
10. Implement `app/services/agent_task.py` (all DB helpers)
11. Test: Create a protected test endpoint, verify JWT works with a real Supabase token

### Step 3: Tools (Day 2)
12. Implement `app/tools/tavily.py`
13. Implement `app/tools/serper.py`
14. Implement `app/tools/github.py`
15. Test each tool independently with sample queries

### Step 4: Models + Prompts (Day 2-3)
16. Implement `app/models/domain.py` (all Pydantic models)
17. Implement `app/models/database.py`, `requests.py`, `responses.py`
18. Implement `app/agents/prompts.py` (all 3 system prompts)

### Step 5: Agents + Pipeline (Day 3-4)
19. Implement `app/agents/decompose.py` (Stage 1)
20. Test Stage 1 with real onboarding data -- verify TopicTree output is sensible
21. Implement `app/agents/research.py` (Stage 2)
22. Test Stage 2 with a single topic group -- verify sources are real URLs
23. Implement `app/agents/synthesize.py` (Stage 3)
24. Implement `app/agents/pipeline.py` (orchestrator)
25. Test full pipeline end-to-end -- watch agent_tasks update in Supabase dashboard

### Step 6: Endpoint + Frontend (Day 4-5)
26. Implement `app/routers/agents.py` (POST /agents/research, GET /agents/status)
27. Add `NEXT_PUBLIC_BACKEND_URL` to Next.js `.env.local`
28. Add the research trigger call to `review/page.tsx`
29. End-to-end test: complete onboarding, watch agents page update in real-time

### Step 7: Deploy (Day 5)
30. Create `Dockerfile` and `render.yaml`
31. Deploy to Render free tier
32. Update `NEXT_PUBLIC_BACKEND_URL` to the Render URL
33. Test in production

### `backend/requirements.txt`

```
fastapi>=0.115.0
uvicorn[standard]>=0.34.0
pydantic>=2.0.0
pydantic-settings>=2.0.0
pydantic-ai[google]>=0.1.0
supabase>=2.0.0
tavily-python>=0.5.0
httpx>=0.28.0
python-jose[cryptography]>=3.3.0
python-dotenv>=1.0.0
```

### `backend/Dockerfile`

```dockerfile
FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### `backend/render.yaml`

```yaml
services:
  - type: web
    name: pedagora-backend
    runtime: docker
    plan: free
    envVars:
      - key: SUPABASE_URL
        sync: false
      - key: SUPABASE_SERVICE_ROLE_KEY
        sync: false
      - key: SUPABASE_JWT_SECRET
        sync: false
      - key: GOOGLE_API_KEY
        sync: false
      - key: TAVILY_API_KEY
        sync: false
      - key: SERPER_API_KEY
        sync: false
      - key: GITHUB_TOKEN
        sync: false
      - key: ENVIRONMENT
        value: production
      - key: FRONTEND_URL
        value: https://pedagora.vercel.app
```

---

## Design Decisions Summary

| Decision | Choice | Rationale |
|---|---|---|
| Background task mechanism | FastAPI `BackgroundTasks` | No separate worker needed on Render free tier. Pipeline returns 202 immediately. |
| Progress communication | Supabase Realtime (via DB updates) | Frontend already subscribes. No SSE or WebSocket from FastAPI needed. |
| Agent framework | PydanticAI | Type-safe outputs via Pydantic models, built-in ReAct loop, usage limits, model-agnostic. |
| Pipeline stages | 3-stage (Decompose, Research, Synthesize) | Decompose and Synthesize are single LLM calls (fast, cheap). Research is the only stage that uses tools (bounded per topic). |
| Per-topic failure handling | Continue on failure | One bad topic should not kill the entire research run. Log it and move on. |
| Trigger mechanism | Fire-and-forget fetch from review page | Non-blocking. User sees agents page immediately. Cold start delay is acceptable. |
| Research output storage | Two tables (sources + results) | Normalized sources for future querying. Single result document for downstream agents. |
| Dropped Exa search | Not included | Tavily + Serper + GitHub provide sufficient coverage. Exa can be added later as a 4th tool. |

---

### Critical Files for Implementation
- `C:\Programming\MyProjects\Pedagora\src\app\(onboarding)\onboarding\review\page.tsx` - The trigger point: add the fire-and-forget fetch call to POST /agents/research after agent task creation (after line 128)
- `C:\Programming\MyProjects\Pedagora\supabase\migrations\00001_initial_schema.sql` - Reference for existing schema, ENUMs, and RLS patterns to follow when creating 00004_add_research_sources.sql
- `C:\Programming\MyProjects\Pedagora\src\types\database.ts` - Must add TypeScript interfaces for ResearchSource and ResearchResult to match the new tables, and the AgentTask/AgentLog interfaces define the exact contract the backend must write to
- `C:\Programming\MyProjects\Pedagora\src\hooks\use-realtime.ts` - The realtime subscription that receives backend updates; confirms the backend must update agent_tasks rows (not send WebSocket messages directly) for the frontend to react
- `C:\Programming\MyProjects\Pedagora\docs\agents\research-agent-deep-dive.md` - The existing design document that this plan refines into implementation-ready specifications; should be updated after implementation to reflect actual architecture