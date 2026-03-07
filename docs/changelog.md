# Changelog

Log of significant changes to the Pedagora codebase. Updated whenever a notable change is made.

---

## 2026-03-07 — Docs Reorganization

Reorganized `docs/` from a flat structure into subdirectories by domain:
- `frontend/` — components, styling, state management, types and validation
- `backend/` — auth and middleware, database
- `agents/` — realtime (will grow with Layer 2)
- `features/` — onboarding (end-to-end feature docs)

`architecture.md` and `changelog.md` remain at the docs root as project-wide files. Each subdirectory has its own `README.md` index. No content changes to moved files.

---

## 2026-03-07 — Onboarding UX Overhaul

### Goal Page: Exam Prep Toggle Redesign

**Files changed:** `src/app/(onboarding)/onboarding/goal/page.tsx`

- Replaced the subtle `Switch` component with a full-width clickable card toggle
- The entire card is clickable (not just a tiny switch)
- Active state uses `border-primary ring-1 ring-primary` (same pattern as preference cards)
- Visual checkbox icon with checkmark when active
- Contextual calendar icon (`event` / `event_available`)
- Removed `Switch` import (no longer used on this page)

### Preferences Page: Cards + Optional Text

**Files changed:** `src/app/(onboarding)/onboarding/preferences/page.tsx`

- Added a `Textarea` below each of the 5 card grid sections
- Users can now elaborate on their card selection in free text
- 5 new `useState` hooks for note state (`styleNote`, `depthNote`, `teachingNote`, `assessmentNote`, `educationNote`)
- Notes are saved to the Zustand store alongside card selections

### New Fields Added Across the Stack

**Types:**
- `src/types/onboarding.ts` — Added `learningStyleNote`, `contentDepthNote`, `teachingStyleNote`, `assessmentTypeNote`, `educationLevelNote` to `OnboardingPreferencesData`
- `src/types/database.ts` — Added `learning_style_note`, `content_depth_note`, `teaching_style_note`, `assessment_type_note`, `education_level_note` to `UserPreferences`

**Validation:**
- `src/lib/validations/onboarding.ts` — Added 5 `z.string()` note fields to `preferencesSchema`

**Store:**
- `src/stores/onboarding-store.ts` — Added empty string defaults for all 5 note fields in `initialPreferences`

**Database:**
- `supabase/migrations/00002_add_preference_notes.sql` — **NEW FILE** — `ALTER TABLE user_preferences ADD COLUMN` for 5 `TEXT NOT NULL DEFAULT ''` columns

### Review Page: Notes Display + DB Write

**Files changed:** `src/app/(onboarding)/onboarding/review/page.tsx`

- Preference notes shown as italic quoted text below each preference value
- Education level note shown in its own row below the grid
- `upsert` call to `user_preferences` now includes all 5 `*_note` fields

---

## Layer 1 Complete — Foundation + Auth + Onboarding + Dashboard + Agents

Initial implementation of the full frontend shell:
- 4 route groups with layouts
- Supabase auth (email/password + OAuth callback)
- Middleware route protection with onboarding enforcement
- 5-step onboarding wizard with Zustand persistence
- Dashboard with demo data
- Agents page with real-time subscription
- shadcn/ui component library
- Dark/light theme system
