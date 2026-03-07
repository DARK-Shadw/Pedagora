# Types & Validation

## Type Files

### `src/types/index.ts` — Enum Types

String union types that match PostgreSQL ENUM columns:

```ts
export type LearningStyle = "visual" | "depth_first" | "fast_paced" | "balanced";
export type ContentDepth = "overview" | "intermediate" | "deep_dive";
export type TeachingStyle = "socratic" | "lecture" | "example_based" | "project_based";
export type AssessmentType = "quiz" | "project" | "mixed" | "none";
export type EducationLevel = "high_school" | "undergraduate" | "graduate" | "postgraduate" | "professional" | "self_learner";
export type AgentType = "research" | "planning" | "visualization" | "teaching";
export type AgentTaskStatus = "queued" | "active" | "completed" | "failed";
// ... and more
```

These are used by both `database.ts` (DB row types) and `onboarding.ts` (form types).

### `src/types/database.ts` — Database Row Interfaces

Each interface maps 1:1 to a Supabase table. Uses `snake_case` to match PostgreSQL columns.

| Interface | Table | Key Fields |
|---|---|---|
| `Profile` | `profiles` | `id`, `name`, `email`, `onboarding_status` |
| `UserPreferences` | `user_preferences` | `learning_style`, `content_depth`, `*_note` fields |
| `LearningGoal` | `learning_goals` | `title`, `end_goal`, `is_exam_prep` |
| `Prerequisite` | `prerequisites` | `skill_name`, `confidence_level` |
| `PrerequisiteAssessment` | `prerequisite_assessments` | `questions`, `score`, `readiness_level` |
| `Course` | `courses` | `title`, `status`, `curriculum`, `progress_percentage` |
| `Lesson` | `lessons` | `title`, `lesson_type`, `content`, `is_completed` |
| `Session` | `sessions` | `session_type`, `status`, `scheduled_at` |
| `AgentTask` | `agent_tasks` | `agent_type`, `status`, `progress_percentage`, `logs` |
| `AgentLog` | (embedded in AgentTask) | `timestamp`, `agent`, `message`, `level` |

### `src/types/onboarding.ts` — Frontend Form Shapes

Uses `camelCase` because they're used in React forms and Zustand. The review page maps these to `snake_case` when writing to the DB.

```ts
interface OnboardingPreferencesData {
  learningStyle: LearningStyle;      // card selection (enum)
  learningStyleNote: string;          // free-text elaboration
  contentDepth: ContentDepth;
  contentDepthNote: string;
  // ... same pattern for teachingStyle, assessmentType, educationLevel
}
```

### Naming Convention: camelCase vs snake_case

- **Frontend** (types/onboarding.ts, stores, forms): `camelCase` — `learningStyle`, `isExamPrep`
- **Database** (types/database.ts, Supabase queries): `snake_case` — `learning_style`, `is_exam_prep`
- The mapping happens in the review page's submission handler where store data is written to DB

## Zod Validation Schemas

### `src/lib/validations/auth.ts`

```ts
loginSchema   → { email: z.string().email(), password: z.string().min(6) }
signupSchema  → { name, email, password, confirmPassword } + .refine() for password match
```

### `src/lib/validations/onboarding.ts`

```ts
goalSchema          → { title: min(3), endGoal, motivation, isExamPrep, examName, examDate }
preferencesSchema   → { learningStyle: z.enum([...]), ..., learningStyleNote: z.string(), ... }
prerequisitesSchema → { prerequisites: z.array({ skillName, confidenceLevel, notes }) }
timelineSchema      → { targetDate, hoursPerWeek: 1-40, sessionFrequency, sessionDurationMinutes: 15-180 }
```

### How Zod Integrates with React Hook Form

```tsx
import { zodResolver } from "@hookform/resolvers/zod";
import { goalSchema, type GoalInput } from "@/lib/validations/onboarding";

const { register, handleSubmit, formState: { errors } } = useForm<GoalInput>({
  resolver: zodResolver(goalSchema),
  defaultValues: { ... },
});
```

- `zodResolver` validates form data against the schema on submit
- `GoalInput` is inferred from the schema via `z.infer<typeof goalSchema>`
- Validation errors are automatically populated in `errors` object
- `register("fieldName")` returns `{ onChange, onBlur, name, ref }` spread onto inputs

### Which Onboarding Pages Use RHF vs useState

| Page | Method | Why |
|---|---|---|
| Goal | React Hook Form | Has required field validation (title min 3 chars) |
| Preferences | `useState` | Card selection + textareas, no complex validation needed |
| Prerequisites | React Hook Form | Dynamic array of fields with validation |
| Timeline | `useState` | Slider/picker UI, all values always valid |
| Review | Neither | Read-only display |
