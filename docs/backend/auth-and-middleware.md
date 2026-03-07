# Authentication & Middleware

## Overview

Pedagora uses **Supabase Auth** for authentication. The auth flow is:

1. User signs up/logs in via email+password
2. Supabase issues a session (stored as HTTP cookies)
3. Middleware refreshes the session on every request and enforces route protection
4. After login, middleware checks `profiles.onboarding_status` to decide where to redirect

## Three Supabase Clients

There are three separate Supabase client factories because cookies are accessed differently in each environment:

### 1. Browser Client — `src/lib/supabase/client.ts`

```ts
"use client";
import { createBrowserClient } from "@supabase/ssr";
export function createClient() {
  return createBrowserClient(SUPABASE_URL, SUPABASE_ANON_KEY);
}
```

- Used in `"use client"` components
- Reads cookies automatically from the browser
- Used by: login/signup forms, `useUser()` hook, `useAgentRealtime()`, review page submission

### 2. Server Client — `src/lib/supabase/server.ts`

```ts
import { createServerClient } from "@supabase/ssr";
import { cookies } from "next/headers";
export async function createClient() {
  const cookieStore = await cookies();
  return createServerClient(SUPABASE_URL, SUPABASE_ANON_KEY, {
    cookies: { getAll, setAll }
  });
}
```

- Used in Server Components, Route Handlers, and Server Actions
- Accesses cookies via `next/headers`
- The `setAll` has a try/catch because Server Components can read cookies but can't set them (that's handled by middleware)
- Used by: `callback/route.ts`

### 3. Middleware Client — `src/lib/supabase/middleware.ts`

```ts
import { createServerClient } from "@supabase/ssr";
export async function updateSession(request: NextRequest) {
  // Creates client with manual cookie management on request/response
}
```

- Used exclusively by `middleware.ts`
- Must manually sync cookies between the request and the response
- This is the only place where session refresh happens

### Why Three Clients?

The Supabase session is stored in cookies. But the way you read/write cookies differs:
- **Browser**: automatic (document.cookie)
- **Server Component**: `cookies()` from `next/headers` (read-only in RSC)
- **Middleware**: manual manipulation of `NextRequest`/`NextResponse` cookies

All three use the same `NEXT_PUBLIC_SUPABASE_URL` and `NEXT_PUBLIC_SUPABASE_ANON_KEY` env vars.

## Middleware Route Protection

**File:** `middleware.ts` + `src/lib/supabase/middleware.ts`

The middleware runs on every request except static files. The `matcher` config:

```ts
"/((?!_next/static|_next/image|favicon.ico|icons/|UIReference/).*)"
```

### Protection Logic

```
Request comes in
│
├── Refresh Supabase session (always)
│
├── Is it a public route (/, /_next, /api, /favicon.ico)?
│   └── Yes → pass through
│
├── Is user NOT logged in + route is protected?
│   └── Yes → redirect to /login
│
├── Is user logged in + on auth route (/login, /signup)?
│   ├── Onboarding completed → redirect to /dashboard
│   └── Onboarding not completed → redirect to /onboarding/goal
│
├── Is user logged in + on app route + onboarding not completed?
│   └── Yes → redirect to /onboarding/goal
│
└── Otherwise → pass through
```

### Protected Routes

Defined in `src/lib/constants.ts`:

```ts
export const PROTECTED_ROUTES = [
  "/dashboard", "/courses", "/sessions",
  "/agents", "/insights", "/settings", "/onboarding"
];
```

## Auth Forms

### Login (`src/app/(auth)/login/page.tsx`)

- Uses React Hook Form + Zod (`loginSchema`)
- Calls `supabase.auth.signInWithPassword({ email, password })`
- On success: `router.push("/dashboard")` + `router.refresh()`
- The `router.refresh()` is important — it forces the middleware to re-run and check onboarding status

### Signup (`src/app/(auth)/signup/page.tsx`)

- Same pattern, uses `signupSchema` (with password confirmation via `.refine()`)
- Calls `supabase.auth.signUp({ email, password, options: { data: { name } } })`

### OAuth Callback (`src/app/(auth)/callback/route.ts`)

- This is a **Route Handler** (not a page)
- Receives the auth code from OAuth providers
- Exchanges code for session via `supabase.auth.exchangeCodeForSession(code)`
- Then checks `profiles.onboarding_status` to redirect to either `/onboarding/goal` or `/dashboard`

## useUser Hook

**File:** `src/hooks/use-user.ts`

```ts
export function useUser() {
  // Returns { user, profile, loading }
}
```

- Fetches the current user + their profile on mount
- Subscribes to `onAuthStateChange` for real-time auth state updates
- Cleans up subscription on unmount
- Used by: `AppTopbar` (shows user name), `AgentsPage` (fetches user's tasks)
