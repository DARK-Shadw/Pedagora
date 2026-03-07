# State Management

## Overview

Pedagora uses **Zustand** for client-side state. There are three stores:

| Store | File | Persisted? | Purpose |
|---|---|---|---|
| `useThemeStore` | `src/stores/theme-store.ts` | Yes (`pedagora-theme`) | Dark/light mode |
| `useOnboardingStore` | `src/stores/onboarding-store.ts` | Yes (`pedagora-onboarding`) | Wizard form data |
| `useAgentStore` | `src/stores/agent-store.ts` | No | Real-time agent tasks |

## Zustand Basics

Zustand stores are created with `create()` and used as hooks:

```ts
// Define
export const useThemeStore = create<ThemeState>()((set) => ({
  theme: "dark",
  setTheme: (theme) => set({ theme }),
}));

// Use in components
const theme = useThemeStore((s) => s.theme);
const setTheme = useThemeStore((s) => s.setTheme);
```

The `(s) => s.theme` selector pattern ensures the component only re-renders when `theme` changes, not when other state changes.

## Theme Store

**File:** `src/stores/theme-store.ts`

```ts
interface ThemeState {
  theme: "light" | "dark" | "system";
  setTheme: (theme: Theme) => void;
}
```

- Persisted to `localStorage` under `"pedagora-theme"` key
- Default: `"dark"`
- Consumed by `ThemeProvider` which adds/removes `dark` class on `<html>`
- The `"system"` option uses `window.matchMedia("(prefers-color-scheme: dark)")` with a listener for changes

## Onboarding Store

**File:** `src/stores/onboarding-store.ts`

```ts
interface OnboardingState {
  currentStep: number;
  goal: OnboardingGoalData;
  preferences: OnboardingPreferencesData;
  prerequisites: OnboardingPrerequisitesData;
  timeline: OnboardingTimelineData;
  setGoal / setPreferences / setPrerequisites / setTimeline / setCurrentStep / reset
}
```

- Persisted to `localStorage` under `"pedagora-onboarding"` key
- Each onboarding page reads from the store as default values on mount
- Each page writes to the store when user clicks "Continue"
- This means navigating back/forward preserves all answers
- `reset()` clears everything — called after successful submission on the review page

### Data Flow

```
Goal page              Preferences page         Review page
    │                      │                        │
    ├─ reads store ←───────┤                        │
    │                      ├─ reads store ←─────────┤
    ├─ setGoal() ──────────┤                        │
    │                      ├─ setPreferences() ─────┤
    │                      │                        ├─ reads all stores
    │                      │                        ├─ writes to Supabase
    │                      │                        └─ reset()
```

### Initial Values

```ts
const initialPreferences = {
  learningStyle: "visual",
  contentDepth: "intermediate",
  teachingStyle: "socratic",
  assessmentType: "mixed",
  educationLevel: "self_learner",
  learningStyleNote: "",
  contentDepthNote: "",
  teachingStyleNote: "",
  assessmentTypeNote: "",
  educationLevelNote: "",
};
```

## Agent Store

**File:** `src/stores/agent-store.ts`

```ts
interface AgentState {
  tasks: AgentTask[];
  setTasks: (tasks: AgentTask[]) => void;
  updateTask: (task: AgentTask) => void;
}
```

- **Not persisted** — agent tasks are fetched from DB on mount
- `setTasks()` — replaces the entire array (used on initial fetch)
- `updateTask()` — replaces a single task by ID (used by real-time updates)
- Updated by the `useAgentRealtime` hook which subscribes to Supabase Realtime

### Real-time Update Flow

```
Supabase DB (agent_tasks row changes)
    │
    ▼
Supabase Realtime (postgres_changes subscription)
    │
    ▼
useAgentRealtime hook (receives payload)
    │
    ▼
agentStore.updateTask(payload.new)
    │
    ▼
AgentsPage re-renders with new data
```
