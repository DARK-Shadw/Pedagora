# Architecture

## Tech Stack

| Layer | Technology |
|---|---|
| Framework | Next.js 16 (App Router, Turbopack) |
| Language | TypeScript (strict mode) |
| Styling | Tailwind CSS v4 |
| UI Primitives | shadcn/ui (Radix + CVA) |
| State | Zustand (with persist middleware) |
| Forms | React Hook Form + Zod |
| Backend | Supabase (Auth, PostgreSQL, RLS, Realtime) |
| Package Manager | pnpm |

## Project Structure

```
pedagora/
├── middleware.ts                    # Route protection + session refresh
├── next.config.ts                   # Next.js config (currently empty)
├── tsconfig.json                    # TypeScript config (strict, path aliases)
├── docs/                            # This documentation
├── supabase/migrations/             # SQL migration files
├── src/
│   ├── app/
│   │   ├── layout.tsx               # Root layout (fonts, ThemeProvider)
│   │   ├── globals.css              # Design tokens + Tailwind v4 config
│   │   ├── error.tsx                # Global error boundary
│   │   ├── not-found.tsx            # 404 page
│   │   ├── (marketing)/             # Public landing page
│   │   │   ├── layout.tsx           # MarketingHeader + MarketingFooter
│   │   │   └── page.tsx             # Landing page (/)
│   │   ├── (auth)/                  # Authentication pages
│   │   │   ├── layout.tsx           # Logo + centered card
│   │   │   ├── login/page.tsx       # Login form
│   │   │   ├── signup/page.tsx      # Signup form
│   │   │   └── callback/route.ts    # OAuth callback (Route Handler)
│   │   ├── (onboarding)/            # 5-step onboarding wizard
│   │   │   ├── layout.tsx           # Logo + centered wizard + gradient
│   │   │   └── onboarding/
│   │   │       ├── page.tsx         # Redirect to /goal
│   │   │       ├── goal/page.tsx
│   │   │       ├── preferences/page.tsx
│   │   │       ├── prerequisites/page.tsx
│   │   │       ├── timeline/page.tsx
│   │   │       └── review/page.tsx
│   │   └── (app)/                   # Authenticated app
│   │       ├── layout.tsx           # Sidebar + Topbar
│   │       ├── loading.tsx          # Loading skeleton
│   │       ├── dashboard/page.tsx
│   │       ├── courses/page.tsx
│   │       ├── courses/[courseId]/page.tsx
│   │       ├── agents/page.tsx
│   │       ├── agents/[taskId]/page.tsx
│   │       ├── sessions/page.tsx
│   │       ├── insights/page.tsx
│   │       └── settings/page.tsx
│   ├── components/
│   │   ├── ui/                      # shadcn/ui primitives
│   │   ├── shared/                  # Logo, MaterialIcon, ThemeProvider, ThemeToggle
│   │   ├── layout/                  # AppSidebar, AppTopbar, MarketingHeader/Footer
│   │   └── onboarding/             # ProgressHeader
│   ├── config/                      # Static config (nav items, onboarding steps, site)
│   ├── hooks/                       # useUser, useAgentRealtime
│   ├── lib/
│   │   ├── supabase/                # 3 Supabase clients
│   │   ├── validations/             # Zod schemas
│   │   ├── utils.ts                 # cn() helper
│   │   └── constants.ts             # Route constants
│   ├── stores/                      # Zustand stores
│   └── types/                       # TypeScript types
```

## Route Groups

Next.js App Router uses `(parentheses)` folders to group routes without affecting the URL path. Each group has its own `layout.tsx`.

| Group | Layout | URLs | Purpose |
|---|---|---|---|
| `(marketing)` | Header + Footer | `/` | Public landing page |
| `(auth)` | Logo + centered card | `/login`, `/signup`, `/callback` | Authentication |
| `(onboarding)` | Logo + centered 640px wizard | `/onboarding/*` | 5-step setup wizard |
| `(app)` | Sidebar + Topbar | `/dashboard`, `/courses`, `/agents`, etc. | Main application |

## Layout Nesting

```
Root layout (src/app/layout.tsx)
├── ThemeProvider wraps everything
├── Inter font loaded via next/font
├── JetBrains Mono + Material Symbols loaded via CDN
│
├── (marketing)/layout.tsx
│   └── MarketingHeader + page + MarketingFooter
│
├── (auth)/layout.tsx
│   └── Logo header + centered max-w-md card
│
├── (onboarding)/layout.tsx
│   └── Logo header + centered max-w-[640px] + decorative gradient
│
└── (app)/layout.tsx
    └── AppSidebar + (AppTopbar + page content + footer)
```

## Path Aliases

Configured in `tsconfig.json`:

```json
{ "paths": { "@/*": ["./src/*"] } }
```

All imports use `@/` instead of relative paths:
```ts
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
```

## Server vs. Client Components

- **Server Components** (default) — `layout.tsx` files in `(auth)`, `(marketing)`, `(onboarding)` are server components. They can be `async` and use `await`.
- **Client Components** — Any file with `"use client"` at the top. Required for: hooks (`useState`, `useEffect`), event handlers, browser APIs, Zustand stores.
- **Route Handlers** — `route.ts` files (like `callback/route.ts`) run on the server and handle HTTP requests directly.

The `(app)/layout.tsx` is a client component because it manages sidebar toggle state.
