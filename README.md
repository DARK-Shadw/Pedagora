# Pedagora

AI-powered education platform with interactive, visual teaching — not just text-chat tutoring.

## Prerequisites

- **Node.js** >= 18 and **pnpm** (frontend)
- **Python** >= 3.12 (backend)
- **Supabase** project (Auth + PostgreSQL + Storage)

## Environment Setup

### Frontend (`/.env.local`)

Copy the example and fill in your values:

```bash
cp .env.local.example .env.local
```

| Variable | Description |
|---|---|
| `NEXT_PUBLIC_SUPABASE_URL` | Your Supabase project URL |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | Supabase anon/public key |
| `SUPABASE_SERVICE_ROLE_KEY` | Supabase service role key (server-side only) |
| `GOOGLE_API_KEY` | Google AI (Gemini) API key |
| `NEXT_PUBLIC_BACKEND_URL` | Backend URL — default `http://localhost:8000` |

### Backend (`/backend/.env`)

Copy the example and fill in your values:

```bash
cp backend/.env.example backend/.env
```

| Variable | Required | Description |
|---|---|---|
| `SUPABASE_URL` | Yes | Your Supabase project URL |
| `SUPABASE_SERVICE_ROLE_KEY` | Yes | Supabase service role key |
| `SUPABASE_JWT_SECRET` | Yes | JWT secret from Supabase dashboard (Settings > API) |
| `GOOGLE_API_KEY` | Yes | Google AI (Gemini) API key |
| `POLLINATIONS_API_KEY` | Yes | Pollinations API key (used for LLM pipeline stages) |
| `TAVILY_API_KEY` | Yes | Tavily search API key |
| `SERPER_API_KEY` | Yes | Serper search API key |
| `GITHUB_TOKEN` | Yes | GitHub personal access token (for code search) |
| `GROQ_API_KEY` | No | Groq API key — falls back to Gemini if empty |
| `FRONTEND_URL` | No | Frontend URL — default `http://localhost:3000` |

You can also override per-stage LLM models via `DECOMPOSE_MODEL`, `EXTRACT_MODEL`, `SYNTHESIZE_MODEL` (defaults to `pollinations:qwen-coder`).

## Running the Project

### Frontend

```bash
pnpm install
pnpm dev
```

Runs on [http://localhost:3000](http://localhost:3000) with Turbopack.

### Backend

```bash
cd backend
pip install -e .
uvicorn app.main:app --reload
```

Runs on [http://localhost:8000](http://localhost:8000).

> **Tip:** Use a Python virtual environment (`python -m venv .venv && source .venv/bin/activate` or `.venv\Scripts\activate` on Windows) before installing dependencies.

## Database

Run the Supabase migrations in order:

```
supabase/migrations/00001_initial_schema.sql
supabase/migrations/00004_add_research_tables.sql
supabase/migrations/00005_upgrade_research_v2.sql
supabase/migrations/00006_add_user_resources.sql
supabase/migrations/00007_add_rag_tables.sql
```

If using the Supabase CLI: `supabase db push`

## Tech Stack

- **Frontend:** Next.js 16, TypeScript, Tailwind v4, shadcn/ui, Zustand, Supabase SSR
- **Backend:** FastAPI, PydanticAI, multi-provider LLM (Pollinations/Gemini/Groq)
- **Database:** Supabase (PostgreSQL + pgvector + RLS)
- **Search:** Tavily + Serper + GitHub API
- **RAG:** Docling parser, Jina v3 embeddings, hybrid search (vector + full-text + RRF)
