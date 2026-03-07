# Onboarding Flow

## Overview

The onboarding is a 5-step wizard that collects user preferences and learning goals, then writes everything to Supabase and launches AI agents.

```
/onboarding/goal → /onboarding/preferences → /onboarding/prerequisites → /onboarding/timeline → /onboarding/review
     Step 0              Step 1                    Step 2                     Step 3                  Step 4
```

Steps are defined in `src/config/onboarding-steps.ts`.

All pages share the `(onboarding)/layout.tsx` — a centered 640px column with a logo header and decorative gradient.

## State Persistence

All wizard data is stored in `useOnboardingStore` (Zustand, persisted to `localStorage`). This means:
- Navigating back/forward preserves answers
- Refreshing the page preserves answers
- Data is only cleared after successful submission (`reset()`)

## Step 0: Goal (`goal/page.tsx`)

**What it collects:** What the user wants to learn.

| Field | Type | Required | Notes |
|---|---|---|---|
| `title` | Textarea | Yes (min 3 chars) | Main learning goal |
| `endGoal` | Input | No | Specific end goal |
| `motivation` | Input | No | Why they're learning |
| `isExamPrep` | Toggle card | No | Clickable card with checkbox |
| `examName` | Input | Conditional | Only shown if `isExamPrep` is true |
| `examDate` | Date input | Conditional | Only shown if `isExamPrep` is true |

**Implementation details:**
- Uses React Hook Form + Zod for validation
- The exam prep toggle is a full-width clickable card (not a small Switch), with `border-primary ring-1 ring-primary` when active
- `watch("isExamPrep")` controls conditional rendering of exam fields
- `setValue("isExamPrep", !isExamPrep)` toggles the value on card click

## Step 1: Preferences (`preferences/page.tsx`)

**What it collects:** How the user learns best.

5 sections, each with a **card grid** (quick select) + **textarea** (optional elaboration):

| Section | Options | Grid |
|---|---|---|
| Learning Style | visual, depth_first, fast_paced, balanced | 2x4 cards with icons |
| Content Depth | overview, intermediate, deep_dive | 3-col cards |
| Teaching Style | socratic, lecture, example_based, project_based | 2-col cards |
| Assessment Type | quiz, project, mixed, none | 4-col compact cards |
| Education Level | high_school through self_learner (6 options) | 3-col compact cards |

**Implementation details:**
- Uses `useState` for each preference (not React Hook Form)
- 5 additional `useState` hooks for the `*Note` text fields
- Both card selections and notes are saved to the Zustand store on "Continue"
- Textarea placeholder: "Want to elaborate? Describe your ... in detail..."

## Step 2: Prerequisites (`prerequisites/page.tsx`)

**What it collects:** What the user already knows.

- Dynamic list of prerequisite skills
- Each skill has: `skillName` (text), `confidenceLevel` (none/beginner/intermediate/advanced), `notes` (text)
- Users can add/remove skills
- Uses React Hook Form with `useFieldArray` for the dynamic list

## Step 3: Timeline (`timeline/page.tsx`)

**What it collects:** Schedule preferences.

| Field | Type | Range |
|---|---|---|
| `targetDate` | Date input | Any future date |
| `hoursPerWeek` | Slider | 1-40 |
| `sessionFrequency` | Card selection | daily, every_other_day, three_per_week, weekly |
| `sessionDurationMinutes` | Slider | 15-180 |

## Step 4: Review (`review/page.tsx`)

**What it does:**
1. Displays a summary of all collected data in `ReviewSection` cards
2. Shows preference notes as italic quoted text when non-empty
3. On "Launch AI Agents", writes everything to Supabase in sequence

### Submission Sequence

```
1. Update profiles.onboarding_status → "in_progress"
2. Insert into learning_goals (returns goal ID)
3. Upsert into user_preferences (includes all *_note fields)
4. Insert into prerequisites (using goal ID from step 2)
5. Insert 4 agent_tasks (research, planning, visualization, teaching)
6. Update profiles.onboarding_status → "completed"
7. reset() onboarding store
8. Redirect to /agents
```

### ReviewSection Component

A local component defined at the bottom of `review/page.tsx`:

```tsx
function ReviewSection({ title, icon, editHref, children }) {
  // Rounded card with icon, title, "Edit" link, and children content
}
```

Each section links back to its corresponding onboarding step via `editHref`.

## Data Mapping (Frontend → Database)

| Frontend (camelCase) | Database (snake_case) | Table |
|---|---|---|
| `goal.title` | `title` | `learning_goals` |
| `goal.endGoal` | `end_goal` | `learning_goals` |
| `goal.isExamPrep` | `is_exam_prep` | `learning_goals` |
| `preferences.learningStyle` | `learning_style` | `user_preferences` |
| `preferences.learningStyleNote` | `learning_style_note` | `user_preferences` |
| `timeline.hoursPerWeek` | `hours_per_week` | `user_preferences` |
| `prerequisites[].skillName` | `skill_name` | `prerequisites` |
