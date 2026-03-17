# Research Agent — Deep Dive & Implementation Plan

## Table of Contents
1. [How Production Research Agents Work](#1-how-production-research-agents-work)
2. [The ReAct Pattern — Core of Every Agent](#2-the-react-pattern--core-of-every-agent)
3. [Three Approaches to Deep Research](#3-three-approaches-to-deep-research)
4. [Free Search APIs — Complete Comparison](#4-free-search-apis--complete-comparison)
5. [GitHub API for Code Research](#5-github-api-for-code-research)
6. [Python Agent Frameworks](#6-python-agent-frameworks)
7. [FastAPI + Next.js + Supabase Architecture](#7-fastapi--nextjs--supabase-architecture)
8. [Recommended Architecture for Pedagora](#8-recommended-architecture-for-pedagora)
9. [Implementation Strategy](#9-implementation-strategy)

---

## 1. How Production Research Agents Work

### The Core Loop

Every production research agent follows the same fundamental pattern:

```
User Query → Decompose into sub-questions
    → For each sub-question:
        → Search (web, APIs, databases)
        → Extract relevant content
        → Validate / cross-reference claims
        → Score source quality
    → Synthesize findings
    → Output structured result
```

### What Makes It "Production-Level"

1. **Multi-source verification** — Not just "search and summarize". Claims are cross-referenced across multiple sources. Contradictions are surfaced, not hidden.
2. **Source quality scoring** — Each source gets a relevance/credibility score. Academic papers > random blog posts.
3. **Structured output** — Results aren't free text. They're structured data (topics, sources with URLs, key concepts, prerequisite chains).
4. **Progress feedback** — Research takes 30-90+ seconds. Users need real-time progress updates (this is where Supabase Realtime shines).
5. **Graceful failure** — When a search API fails or returns garbage, the agent falls back to other sources, not crashes.
6. **Cost tracking** — Every API call has a cost. Production agents track token usage and API calls per research run.

### How Claude Code's Research Works

Claude Code's deep research uses **multi-agent orchestration**:

1. An **orchestrator** receives the research question
2. It **decomposes** the question into parallel sub-goals
3. **Subagents** are spawned to investigate different angles independently
4. Each subagent decides whether to answer directly or create further sub-agents
5. Results flow back upward through the hierarchy
6. The orchestrator **synthesizes** findings into a structured report

Key insight: Deep research isn't just "search and summarize" — it's **claim verification across multiple sources with reasoning**. Claude's extended thinking makes this effective.

---

## 2. The ReAct Pattern — Core of Every Agent

ReAct = **Re**asoning + **Act**ing. The agent alternates between thinking and doing.

### The Loop (Language-Agnostic Pseudocode)

```
while (not done):
    # REASON: LLM analyzes current state and decides what to do
    response = llm.generate(messages, tools)

    # ACT: If the LLM wants to call a tool, execute it
    if response.has_tool_calls:
        for tool_call in response.tool_calls:
            result = execute(tool_call)
            messages.append(tool_call, result)  # OBSERVE
    else:
        # No tool call = LLM is done, has final answer
        return response.text
```

### In Python (PydanticAI)

```python
from pydantic_ai import Agent
from pydantic import BaseModel

class ResearchOutput(BaseModel):
    topics: list[dict]
    sources: list[dict]
    prerequisite_chain: list[str]

agent = Agent(
    'google-gla:gemini-2.5-flash',
    output_type=ResearchOutput,
    system_prompt='You are a research agent...',
)

@agent.tool
async def web_search(ctx, query: str) -> str:
    """Search the web for information."""
    return await tavily_client.search(query)

@agent.tool
async def github_search(ctx, query: str) -> str:
    """Search GitHub for relevant repositories."""
    return await search_github(query)

result = await agent.run('Research: video diffusion models')
print(result.output)  # Typed ResearchOutput
```

PydanticAI handles the ReAct loop internally — it calls the model, executes tool calls, feeds results back, and repeats until the model produces output matching `output_type`.

### In Python (Raw Google GenAI SDK)

```python
from google import genai
from google.genai import types

client = genai.Client(api_key=GOOGLE_API_KEY)

# Define tools as Python functions — SDK auto-generates schemas
def web_search(query: str) -> dict:
    """Search the web for information about the query."""
    return tavily_client.search(query)

# Automatic function calling — SDK handles the loop
response = client.models.generate_content(
    model='gemini-2.5-flash',
    contents='Research video diffusion models',
    config=types.GenerateContentConfig(
        tools=[web_search],
        # SDK auto-calls functions and feeds results back
    ),
)
print(response.text)  # Final synthesized answer
```

---

## 3. Three Approaches to Deep Research

### Approach A: DIY Recursive Agent Spawning

- Shell scripts (~20 lines), zero dependencies
- Orchestrator spawns parallel researchers
- Each researcher can spawn sub-agents
- Results flow upward
- **Pros**: Maximum flexibility, cheap to start
- **Cons**: Token costs explode with depth, no progress visibility, quality depends entirely on prompts

### Approach B: MCP Tool Servers

- Plug-and-play research tools via Model Context Protocol
- Structured 5-phase methodology: exploration → synthesis → follow-up → analysis → citation
- Tools like DuckDuckGo, Semantic Scholar, Tavily available as MCP servers
- **Pros**: Minimal setup, structured methodology
- **Cons**: Constrained by tool capabilities, 5-10k tokens overhead for tool definitions

### Approach C: Full Production Pipeline (RECOMMENDED FOR PEDAGORA)

```
Source scraping → Claim extraction → Cross-source verification
    → Confidence scoring → Structured output
```

Key production features:
- **Server-sent events** stream progress updates (critical for 30-90s analyses)
- **Per-request cost tracking** from day one
- **Graceful degradation** when APIs fail
- **Domain-specific logic** for different subject areas
- **Contradiction detection** — "If Source A says X, does Source B confirm?"

**Pros**: Complete control, genuine product differentiation, optimized UX
**Cons**: More engineering investment upfront

---

## 4. Free Search APIs — Complete Comparison

### Tier 1: Best for AI Agents (Recommended)

#### Tavily
- **Free tier**: 1,000 credits/month (resets monthly)
- **Paid**: $0.008/request
- **Speed**: ~1.9s average
- **Key feature**: Aggregates up to 20 sources per query, AI-scored and ranked. Returns LLM-ready content, not raw HTML.
- **AI-readiness**: Excellent — 93.3% accuracy on SimpleQA benchmark. Citation-ready output.
- **Python SDK**: `pip install tavily-python` — both sync (`TavilyClient`) and async (`AsyncTavilyClient`)
- **Methods**: `search()`, `extract()`, `crawl()`, `map()`, `get_search_context()`
- **Best for**: Source discovery with credibility assessment
- **Note**: Acquired by Nebius (Feb 2026) — future pricing may change
- **Verdict**: BEST for our use case. Purpose-built for AI agents. Monthly free reset is great.

#### Serper.dev
- **Free tier**: 2,500 queries (one-time, no credit card)
- **Paid**: $1.00/1k queries (drops to $0.30/1k at scale)
- **Speed**: 1-2s average (fastest)
- **Key feature**: Google SERP results across all verticals — Search, Images, News, Scholar, Patents
- **AI-readiness**: Good — clean JSON, but returns SERP metadata, not extracted content
- **Best for**: Google Scholar searches, academic paper discovery
- **Verdict**: BEST for academic/scholarly search. Use alongside Tavily.

#### Exa
- **Free tier**: 1,000 searches/month
- **Paid**: $1.50/1k searches (neural), $5/1k (with content)
- **Speed**: ~1.2s average (fastest for AI)
- **Key feature**: Neural semantic search trained on link prediction. Understands meaning, not just keywords.
- **AI-readiness**: Excellent — embeddings-powered, finds conceptually related content
- **Best for**: Finding similar resources, research papers, niche content
- **Verdict**: GREAT for semantic discovery. More expensive than Tavily for content extraction.

### Tier 2: Budget Options

#### SearXNG (Self-Hosted)
- **Free tier**: Unlimited (self-hosted)
- **Paid**: $0 + server costs
- **Speed**: Variable (depends on upstream engines)
- **Key feature**: Open-source metasearch, aggregates 247+ engines
- **Setup**: Docker container, ~5 minutes. Enable JSON API in settings.yml.
- **AI-readiness**: Low — returns links, no content extraction. Must scrape pages yourself.
- **Best for**: Fallback search when other APIs exhaust free tiers
- **Verdict**: FREE but requires self-hosting and extra scraping work. Good fallback.

### Tier 3: Not Recommended

| API | Why Not |
|-----|---------|
| SerpAPI | 250/month free, $75+/5k paid. Way too expensive. |
| Brave Search | Removed free tier entirely. $5/1k queries. |
| Scrapingbee | 66 free queries. 7s response time. |

### RECOMMENDATION FOR PEDAGORA

**Primary stack (all free tiers combined = ~4,500 searches/month)**:

| API | Role | Free Quota |
|-----|------|------------|
| **Tavily** | General web research, source discovery | 1,000/mo |
| **Serper** | Google Scholar, academic papers, news | 2,500 one-time |
| **Exa** | Semantic search, finding similar content | 1,000/mo |
| **GitHub API** | Code repos, working examples | 5,000 req/hr |

Fallback: SearXNG self-hosted on Docker (unlimited, free)

---

## 5. GitHub API for Code Research

### Rate Limits (Free)
- **Unauthenticated**: 60 requests/hour
- **With Personal Access Token**: 5,000 requests/hour
- **Search endpoint**: 30 requests/minute (separate limit)

### Useful Endpoints

```
# Search repos by topic
GET /search/repositories?q={topic}+language:{lang}&sort=stars

# Search code
GET /search/code?q={query}+repo:{owner}/{repo}

# Get README
GET /repos/{owner}/{repo}/readme

# Get repo topics/tags
GET /repos/{owner}/{repo}/topics
```

### For Pedagora's Research Agent

When a user wants to learn "video diffusion models":
1. Search GitHub for repos: `q=video+diffusion+model&sort=stars&order=desc`
2. For top repos, fetch README content
3. Extract: what the project does, dependencies, architecture patterns
4. These become grounded teaching material

---

## 6. Python Agent Frameworks

### PydanticAI (RECOMMENDED)

**Why PydanticAI for Pedagora:**
- Built by the Pydantic team — same validation philosophy
- Type-safe: `output_type` enforces structured output via Pydantic models
- Model-agnostic: supports Gemini, OpenAI, Anthropic — swap models without code changes
- Dependency injection via `RunContext` — pass Supabase client, API keys, user context
- Built-in cost tracking via `UsageLimits` (request_limit, token_limit, tool_calls_limit)
- `ModelRetry` for self-correction when tools fail
- Native async support — perfect for FastAPI
- Multi-agent support: agent delegation (agent-as-tool) and programmatic hand-off

**Key Concepts:**

```python
from pydantic_ai import Agent, RunContext, ModelRetry
from pydantic import BaseModel
from dataclasses import dataclass

# 1. Define structured output
class ResearchResult(BaseModel):
    topics: list[TopicInfo]
    sources: list[SourceInfo]
    prerequisite_chain: list[str]
    estimated_difficulty: str

# 2. Define dependencies (injected at runtime)
@dataclass
class ResearchDeps:
    supabase: SupabaseClient
    tavily: TavilyClient
    goal_id: str
    user_id: str

# 3. Create the agent
research_agent = Agent(
    'google-gla:gemini-2.5-flash',
    deps_type=ResearchDeps,
    output_type=ResearchResult,
    instructions='You are a research agent for an education platform...',
)

# 4. Register tools
@research_agent.tool
async def web_search(ctx: RunContext[ResearchDeps], query: str) -> str:
    """Search the web for educational resources."""
    response = ctx.deps.tavily.search(query, max_results=5)
    return str(response['results'])

@research_agent.tool
async def log_progress(ctx: RunContext[ResearchDeps], message: str) -> str:
    """Log research progress for the student to see."""
    await ctx.deps.supabase.from_('agent_tasks').update({
        'current_task': message,
        'logs': ...,  # append to JSONB array
    }).eq('goal_id', ctx.deps.goal_id).eq('agent_type', 'research').execute()
    return 'Progress logged.'

# 5. Run with dependencies
result = await research_agent.run(
    f'Research: {goal.title}',
    deps=ResearchDeps(supabase=supa, tavily=tavily, goal_id=gid, user_id=uid),
    usage_limits=UsageLimits(request_limit=15, tool_calls_limit=30),
)
# result.output is a validated ResearchResult
```

**Streaming Events (for real-time UI):**

```python
async for event in research_agent.run_stream_events(prompt, deps=deps):
    if isinstance(event, FunctionToolCallEvent):
        # Tool was called — update UI
        print(f"Agent called: {event.tool_name}")
    elif isinstance(event, AgentRunResultEvent):
        # Final result ready
        final_output = event.result.output
```

**Multi-Agent Delegation:**

```python
# Research agent can delegate to a sub-agent
sub_agent = Agent('google-gla:gemini-2.5-flash', output_type=list[str])

@research_agent.tool
async def find_prerequisites(ctx: RunContext[ResearchDeps], topic: str) -> list[str]:
    """Find prerequisite topics for a given subject."""
    result = await sub_agent.run(
        f'List prerequisites for learning {topic}',
        usage=ctx.usage,  # Aggregates token counts into parent
    )
    return result.output
```

### Google GenAI SDK (Alternative — Lower Level)

**When to use**: If you want maximum control or PydanticAI adds too much overhead.

```python
from google import genai
from google.genai import types

client = genai.Client(api_key=GOOGLE_API_KEY)

# Tools as plain Python functions
def web_search(query: str) -> dict:
    """Search the web for educational resources about the query."""
    return tavily.search(query)

def github_search(query: str, language: str = "") -> dict:
    """Search GitHub repositories for working code examples."""
    return search_github_repos(query, language)

# Automatic tool calling loop
response = client.models.generate_content(
    model='gemini-2.5-flash',
    contents=user_prompt,
    config=types.GenerateContentConfig(
        tools=[web_search, github_search],
        system_instruction='You are a research agent...',
    ),
)
```

The SDK auto-generates function schemas from docstrings/type hints and handles the call→result→re-prompt loop automatically.

**Manual loop** (for progress updates):

```python
contents = [types.Content(role='user', parts=[types.Part(text=prompt)])]
config = types.GenerateContentConfig(
    tools=[tool_declarations],
    system_instruction=system_prompt,
)

for step in range(MAX_STEPS):
    response = client.models.generate_content(
        model='gemini-2.5-flash', contents=contents, config=config
    )

    # Check for tool calls
    part = response.candidates[0].content.parts[0]
    if hasattr(part, 'function_call') and part.function_call:
        fc = part.function_call
        result = execute_tool(fc.name, fc.args)

        # Append model response + tool result
        contents.append(response.candidates[0].content)
        contents.append(types.Content(
            role='user',
            parts=[types.Part.from_function_response(name=fc.name, response=result)]
        ))

        # UPDATE PROGRESS HERE — write to Supabase
        await update_agent_progress(goal_id, f"Step {step}: called {fc.name}")
    else:
        # No tool call — model is done
        final_answer = response.text
        break
```

### LangGraph (Not Recommended for Us)

- Heavy dependency tree (LangChain ecosystem)
- Over-abstracted for our use case
- Lock-in to LangChain's patterns
- PydanticAI gives us the same ReAct loop with less overhead

---

## 7. FastAPI + Next.js + Supabase Architecture

### System Architecture

```
┌─────────────────────────────────────────────────┐
│                   FRONTEND                       │
│            Next.js (Vercel Free)                 │
│  ┌─────────┐ ┌──────────┐ ┌──────────────────┐  │
│  │  Auth   │ │Dashboard │ │  Agents Page     │  │
│  │  Pages  │ │  Pages   │ │  (Realtime UI)   │  │
│  └────┬────┘ └────┬─────┘ └────────┬─────────┘  │
│       │           │                │             │
│       ▼           ▼                ▼             │
│  Supabase Auth  Supabase DB   Supabase Realtime  │
└───────┬───────────┬────────────────┬─────────────┘
        │           │                │
        ▼           ▼                ▼
┌─────────────────────────────────────────────────┐
│              SUPABASE (Free Tier)                 │
│  ┌──────┐ ┌──────────┐ ┌──────────┐ ┌────────┐  │
│  │ Auth │ │PostgreSQL│ │ Realtime │ │  RLS   │  │
│  └──────┘ └──────────┘ └──────────┘ └────────┘  │
└───────────────────┬──────────────────────────────┘
                    │
                    ▼ (service_role key)
┌─────────────────────────────────────────────────┐
│              BACKEND (Python)                    │
│          FastAPI (Render/Fly.io Free)             │
│  ┌───────────────┐  ┌────────────────────────┐   │
│  │  Auth Middle  │  │    Agent Endpoints     │   │
│  │  (JWT verify) │  │  POST /agents/research │   │
│  └───────┬───────┘  │  POST /agents/plan     │   │
│          │          │  GET  /agents/status    │   │
│          ▼          └──────────┬──────────────┘   │
│  ┌───────────────┐            │                  │
│  │  PydanticAI   │◄───────────┘                  │
│  │  Research     │                               │
│  │  Agent        │                               │
│  │  ┌─────────┐  │                               │
│  │  │ Tools:  │  │                               │
│  │  │ Tavily  │  │                               │
│  │  │ Serper  │  │                               │
│  │  │ GitHub  │  │                               │
│  │  │ Exa     │  │                               │
│  │  └─────────┘  │                               │
│  └───────────────┘                               │
└─────────────────────────────────────────────────┘
```

### Auth Flow: Next.js → FastAPI

1. User logs in via Next.js (Supabase Auth)
2. Supabase sets JWT cookie in browser
3. When Next.js calls FastAPI, it sends the JWT as `Authorization: Bearer <token>`
4. FastAPI verifies the JWT using the Supabase JWT secret

**FastAPI JWT Verification:**

```python
from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import jwt, JWTError

security = HTTPBearer()

SUPABASE_JWT_SECRET = os.environ["SUPABASE_JWT_SECRET"]

async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> dict:
    try:
        payload = jwt.decode(
            credentials.credentials,
            SUPABASE_JWT_SECRET,
            algorithms=["HS256"],
            audience="authenticated",
        )
        return payload  # Contains sub (user_id), email, role, etc.
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

# Protected endpoint
@app.post("/agents/research")
async def trigger_research(
    request: ResearchRequest,
    user: dict = Depends(get_current_user),
):
    user_id = user["sub"]
    # ... trigger research agent
```

### FastAPI Talks to Supabase

FastAPI uses the **service_role key** (bypasses RLS) to write agent results:

```python
from supabase import create_client

supabase = create_client(
    os.environ["SUPABASE_URL"],
    os.environ["SUPABASE_SERVICE_ROLE_KEY"],  # bypasses RLS
)

# Write research progress
await supabase.table("agent_tasks").update({
    "status": "active",
    "progress_percentage": 45,
    "current_task": "Searching for academic papers...",
}).eq("goal_id", goal_id).eq("agent_type", "research").execute()
```

### Deployment Options (Free Tier)

| Platform | Free Tier | Timeout | Best For |
|----------|-----------|---------|----------|
| **Render** | 750 hrs/mo, sleeps after 15min idle | None (web service) | Simple deploy, auto-sleep OK for MVP |
| **Fly.io** | 3 shared VMs, 256MB each | None | Low-latency, static IPs |
| **Railway** | $5 credit (one-time) | None | Fast setup, burns through credit |

**Recommendation**: Start with **Render** free tier. Auto-sleep is fine — research is triggered by user action, the cold start (~30s) is acceptable since research itself takes 30-90s.

---

## 8. Recommended Architecture for Pedagora

### Overview

```
Onboarding Complete (Next.js)
    │
    ▼ POST /agents/research (JWT auth)
FastAPI Backend
    │
    ▼
Research Agent (PydanticAI + Gemini 2.5 Flash)
    │
    ├─ Tool: tavily_search(query) — general web research
    ├─ Tool: serper_scholar(query) — academic papers
    ├─ Tool: exa_search(query) — semantic/similar content
    ├─ Tool: github_search(query) — code repos
    ├─ Tool: extract_content(url) — fetch & extract page content
    ├─ Tool: log_progress(message) — update agent_tasks via Supabase
    └─ Output: ResearchResult (Pydantic model — validated structured data)
    │
    ▼
Writes to Supabase (service_role):
    ├─ agent_tasks (status, progress, logs) — real-time UI updates
    └─ research_sources (structured output)
    │
    ▼
Frontend receives real-time updates via Supabase Realtime (already built)
```

### New Database Table: research_sources

```sql
CREATE TABLE research_sources (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  goal_id UUID NOT NULL REFERENCES learning_goals(id) ON DELETE CASCADE,
  user_id UUID NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
  source_type TEXT NOT NULL, -- 'article', 'paper', 'repo', 'tutorial', 'video', 'book'
  title TEXT NOT NULL,
  url TEXT,
  author TEXT,
  summary TEXT,           -- AI-generated summary of why this source matters
  key_concepts JSONB,     -- extracted concepts/topics from this source
  relevance_score NUMERIC(3,2), -- 0.00 to 1.00
  credibility_score NUMERIC(3,2),
  content_extract TEXT,   -- key passages/content extracted
  metadata JSONB,         -- flexible: stars, language, pub_date, etc.
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_research_sources_goal_id ON research_sources(goal_id);
ALTER TABLE research_sources ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Users can view own research sources"
  ON research_sources FOR SELECT USING (auth.uid() = user_id);
CREATE POLICY "Service role can insert research sources"
  ON research_sources FOR INSERT WITH CHECK (true);
```

### Research Agent System Prompt (Draft)

```
You are a Research Agent for Pedagora, an AI education platform.

Your job is to research a learning topic thoroughly and gather HIGH-QUALITY,
REAL sources that a teaching AI can use to create accurate lessons.

## Context
- Student's learning goal: {goal.title}
- End goal: {goal.endGoal}
- Education level: {educationLevel}
- Prerequisites they know: {prerequisites}
- Prerequisites they're weak in: {weakPrerequisites}

## Your Research Process
1. UNDERSTAND the topic scope — what subtopics does this goal encompass?
2. SEARCH for foundational resources (textbooks, courses, official docs)
3. SEARCH for practical resources (GitHub repos, tutorials, examples)
4. SEARCH for academic resources (papers, lectures) if appropriate
5. For each source, EXTRACT key concepts and assess quality
6. IDENTIFY the prerequisite chain — what must be learned first?
7. MAP the topic structure — how do subtopics connect?

## Rules
- ONLY include sources you've actually found and verified via search tools
- NEVER fabricate URLs, authors, or source details
- Prefer sources that match the student's education level
- Prioritize: official docs > textbooks > quality tutorials > blog posts
- For code topics: find repos with stars > 100, recent activity, good READMEs
- Rate each source's relevance (0-1) and credibility (0-1)
- Log your progress as you go so the student sees live updates

## Output
When done, return your structured findings as a ResearchResult.
```

---

## 9. Implementation Strategy

### Phase 1: Backend Foundation
1. Create `backend/` directory with FastAPI project structure
2. Set up Supabase client (service_role) for backend
3. Implement JWT auth middleware (verify Supabase tokens)
4. Create `POST /agents/research` endpoint
5. Create `research_sources` table migration

### Phase 2: Search Tool Wrappers
1. `pip install tavily-python` — wrap `TavilyClient.search()` + `TavilyClient.extract()`
2. Serper wrapper — `httpx` calls to Google Scholar endpoint
3. GitHub wrapper — `httpx` calls to search API with PAT auth
4. (Optional) Exa wrapper

### Phase 3: Research Agent
1. `pip install pydantic-ai` — create research agent with Gemini 2.5 Flash
2. Define `ResearchResult` Pydantic model (structured output)
3. Register tools: web_search, scholar_search, github_search, log_progress
4. Agent writes progress to `agent_tasks` (Supabase Realtime pushes to UI)
5. Agent writes final output to `research_sources`

### Phase 4: Frontend Integration
1. Next.js API route proxies to FastAPI (or direct call with JWT)
2. Trigger research when onboarding completes
3. Agents page already has Realtime — shows live progress
4. Research results viewable on agent detail page

### Phase 5: Hardening
1. Error handling and retries for API failures
2. Fallback search providers when primary exhausts quota
3. Cost tracking per research run (PydanticAI's UsageLimits)
4. Rate limiting per user
5. Deploy to Render free tier

### Python Dependencies

```
# backend/requirements.txt
fastapi>=0.115.0
uvicorn[standard]>=0.34.0
pydantic-ai[google]>=0.1.0
supabase>=2.0.0
tavily-python>=0.5.0
httpx>=0.28.0
python-jose[cryptography]>=3.3.0
python-dotenv>=1.0.0
```

---

## Sources

### Architecture & Patterns
- [Build Production-Ready AI Agents (2026)](https://codingscape.com/blog/build-production-ready-ai-agents-in-2026-without-deleting-your-database)
- [AI Agent Architecture (Redis, 2026)](https://redis.io/blog/ai-agent-architecture/)
- [Building Production ReAct Agents From Scratch](https://www.decodingai.com/p/building-production-react-agents)
- [Three Ways to Build Deep Research with Claude](https://paddo.dev/blog/three-ways-deep-research-claude/)
- [Agentic Design Patterns (2026)](https://www.sitepoint.com/the-definitive-guide-to-agentic-design-patterns-in-2026/)

### PydanticAI
- [PydanticAI Agents Docs](https://ai.pydantic.dev/agent/)
- [PydanticAI Multi-Agent Patterns](https://ai.pydantic.dev/multi-agent-applications/)
- [PydanticAI Toolsets](https://ai.pydantic.dev/toolsets/)
- [PydanticAI Google Model Support](https://ai.pydantic.dev/models/google/)
- [PydanticAI GitHub](https://github.com/pydantic/pydantic-ai)

### Google GenAI
- [Gemini Function Calling Docs](https://ai.google.dev/gemini-api/docs/function-calling)
- [Using Tools & Agents with Gemini](https://ai.google.dev/gemini-api/docs/tools)
- [Google Python GenAI SDK](https://github.com/googleapis/python-genai)

### FastAPI + Supabase
- [Integrating FastAPI with Supabase Auth](https://dev.to/j0/integrating-fastapi-with-supabase-auth-780)
- [Next.js + FastAPI + Supabase: A Powerful Trio](https://ftp.sleeklens.com/master-series/next-js-fastapi-supabase-a-powerful-trio-1764800684)
- [FastAPI + LangGraph Production Template](https://github.com/wassim249/fastapi-langgraph-agent-production-ready-template)

### Search APIs
- [7 Free Web Search APIs for AI Agents (KDnuggets)](https://www.kdnuggets.com/7-free-web-search-apis-for-ai-agents)
- [Best Web Search APIs for AI (2026, Firecrawl)](https://www.firecrawl.dev/blog/best-web-search-apis)
- [SERP API Comparison 2025 (Dev.to)](https://dev.to/ritza/best-serp-api-comparison-2025-serpapi-vs-exa-vs-tavily-vs-scrapingdog-vs-scrapingbee-2jci)
- [Tavily Python SDK Reference](https://docs.tavily.com/sdk/python/reference)
- [Tavily Official](https://www.tavily.com/)
- [Serper Official](https://serper.dev/)
- [SearXNG Docker Setup](https://github.com/searxng/searxng-docker)

### Deployment
- [Deploy FastAPI on Render](https://render.com/docs/deploy-fastapi)
- [Deploy FastAPI on Railway](https://docs.railway.com/guides/fastapi)
- [Deploy FastAPI on Fly.io](https://fly.io/docs/python/frameworks/fastapi/)
- [Python Hosting Options Compared](https://www.nandann.com/blog/python-hosting-options-comparison)

### GitHub API
- [GitHub REST API Rate Limits](https://docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api)
- [GitHub Search API](https://docs.github.com/en/rest/search)
