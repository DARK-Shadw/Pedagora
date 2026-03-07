# Realtime & Agent System

## Overview

Pedagora uses **Supabase Realtime** to push live updates from the database to the frontend. Currently, this is used for the agent task system — when an agent's status or progress changes in the DB, the UI updates instantly without polling.

## How It Works

```
Backend updates agent_tasks row in PostgreSQL
        │
        ▼
Supabase Realtime detects the change (postgres_changes)
        │
        ▼
Broadcasts to subscribed clients via WebSocket
        │
        ▼
useAgentRealtime hook receives the payload
        │
        ▼
Calls agentStore.updateTask(payload.new)
        │
        ▼
React re-renders the AgentsPage
```

## `useAgentRealtime` Hook

**File:** `src/hooks/use-realtime.ts`

```ts
export function useAgentRealtime(userId: string | undefined) {
  const { updateTask } = useAgentStore();

  useEffect(() => {
    if (!userId) return;

    const supabase = createClient();
    const channel = supabase
      .channel("agent-tasks")
      .on("postgres_changes", {
        event: "UPDATE",
        schema: "public",
        table: "agent_tasks",
        filter: `user_id=eq.${userId}`,
      }, (payload) => {
        updateTask(payload.new as AgentTask);
      })
      .subscribe();

    return () => { supabase.removeChannel(channel); };
  }, [userId, updateTask]);
}
```

Key details:
- Only subscribes to `UPDATE` events (not INSERT or DELETE)
- Filters by `user_id` so users only get their own updates
- Cleans up the channel subscription on unmount
- Uses the browser Supabase client (`createClient()`)

## Agent System

### Four Agent Types

| Agent | Purpose | Icon |
|---|---|---|
| `research` | Searches academic sources, indexes papers | `search_insights` |
| `planning` | Builds learning path, maps prerequisites | `account_tree` |
| `visualization` | Generates diagrams, infographics | `polyline` |
| `teaching` | Creates lesson scripts, teaching content | `record_voice_over` |

### Agent Lifecycle

```
queued → active → completed
                → failed
```

All 4 agents are created with `status: "queued"` during onboarding. The backend (Layer 2, not yet built) will process them sequentially or in parallel.

### Agents Page (`src/app/(app)/agents/page.tsx`)

The most feature-complete page in the app. It:

1. Fetches agent tasks from Supabase on mount
2. Falls back to demo data if no real tasks exist
3. Subscribes to real-time updates via `useAgentRealtime`
4. Renders:
   - **Agent cards** (4-column grid) — icon, label, current task, progress bar
   - **Pipeline table** — tabular view of all agents with focus area and progress
   - **Execution logs** — terminal-style log viewer (dark bg, monospace, colored by level)

### Demo Data

When no real agent tasks exist (e.g., during development), the page uses hardcoded demo data defined at the top of the file. The demo shows:
- Research agent: completed (100%)
- Planning agent: active (68%)
- Visualization agent: queued (30%)
- Teaching agent: queued (0%)

### Agent Logs

Each `AgentTask` has a `logs` field (JSONB array) containing entries like:

```ts
interface AgentLog {
  timestamp: string;    // e.g., "12:44:01"
  agent: string;        // e.g., "RESEARCH_AGENT"
  message: string;      // Human-readable status
  level: "info" | "success" | "error" | "system";
}
```

Logs from all agents are merged and sorted by timestamp for the unified log viewer.

## Future: Supabase Realtime for Other Features

The same pattern can be extended for:
- Live lesson sessions (real-time collaboration)
- Course generation progress
- Notification delivery
