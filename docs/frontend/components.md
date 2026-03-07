# Components

## Component Organization

```
src/components/
├── ui/           # Primitive building blocks (shadcn/ui pattern)
├── shared/       # App-wide reusable components
├── layout/       # Structural layout components
└── onboarding/   # Onboarding-specific components
```

## UI Components (`src/components/ui/`)

These follow the **shadcn/ui** pattern: Radix UI primitives styled with Tailwind, using `class-variance-authority` (CVA) for variants.

| Component | Radix Primitive | Key Props |
|---|---|---|
| `button.tsx` | `@radix-ui/react-slot` | `variant`, `size`, `asChild` |
| `input.tsx` | native `<input>` | Standard input props |
| `textarea.tsx` | native `<textarea>` | Standard textarea props |
| `label.tsx` | `@radix-ui/react-label` | Standard label props |
| `select.tsx` | `@radix-ui/react-select` | `SelectTrigger`, `SelectContent`, `SelectItem` |
| `switch.tsx` | `@radix-ui/react-switch` | `checked`, `onCheckedChange` |
| `slider.tsx` | `@radix-ui/react-slider` | `value`, `onValueChange`, `min`, `max` |
| `tabs.tsx` | `@radix-ui/react-tabs` | `TabsList`, `TabsTrigger`, `TabsContent` |
| `card.tsx` | native `<div>` | `CardHeader`, `CardContent`, `CardFooter` |
| `badge.tsx` | native `<div>` | `variant` |
| `progress.tsx` | `@radix-ui/react-progress` | `value` |
| `separator.tsx` | `@radix-ui/react-separator` | `orientation` |
| `skeleton.tsx` | native `<div>` | Animated placeholder |
| `radio-group.tsx` | `@radix-ui/react-radio-group` | `value`, `onValueChange` |

### CVA Pattern (Button Example)

```tsx
const buttonVariants = cva(
  "inline-flex items-center justify-center ...", // base classes
  {
    variants: {
      variant: {
        default: "bg-primary text-white shadow-lg ...",
        outline: "border border-primary/20 ...",
        ghost: "hover:bg-accent ...",
      },
      size: {
        default: "h-10 px-6",
        sm: "h-9 px-4 text-xs",
        lg: "h-14 px-10 text-base rounded-xl",
      },
    },
    defaultVariants: { variant: "default", size: "default" },
  }
);
```

Usage: `<Button variant="outline" size="lg">Click</Button>`

### The `asChild` Pattern

Radix's `Slot` component merges its props into its child. This lets you render a Button that's actually a Link:

```tsx
<Button asChild>
  <Link href="/courses">Go to Courses</Link>
</Button>
```

The Button's classes and styles get applied to the `<Link>`, not a wrapper `<button>`.

### The `cn()` Utility

```ts
import { cn } from "@/lib/utils";
// cn = clsx + tailwind-merge
// Merges class names and resolves Tailwind conflicts
cn("px-4 py-2", isActive && "bg-primary", className)
```

## Shared Components (`src/components/shared/`)

### `MaterialIcon`

Renders Google Material Symbols Outlined icons:

```tsx
<MaterialIcon name="dashboard" className="text-xl" filled />
```

- `name` — the icon name from Google Material Symbols
- `filled` — sets `fontVariationSettings: "'FILL' 1"` for filled variant
- Icons are loaded via CDN in the root layout's `<head>`

### `Logo`

```tsx
<Logo size="md" showText={true} className="..." />
```

Three sizes: `sm` (24px icon), `md` (32px icon), `lg` (40px icon). Shows a primary-colored rounded square with the `auto_awesome` icon + "Pedagora" text.

### `ThemeProvider`

Wraps the entire app in the root layout. Reads `useThemeStore` and:
- `"dark"` → adds `dark` class to `<html>`
- `"light"` → removes `dark` class
- `"system"` → uses `matchMedia` listener to follow OS preference

### `ThemeToggle`

Simple button that cycles between dark and light mode. Shows `light_mode` icon in dark mode and `dark_mode` icon in light mode.

## Layout Components (`src/components/layout/`)

### `AppSidebar`

- 256px wide sidebar (`w-64`)
- Logo + "AI Academy" label at top
- Main nav items from `src/config/navigation.ts` (`appNav`)
- Support section from `appNavSupport`
- Active route highlighted with `bg-primary/10 text-primary`
- "New Inquiry" CTA button at bottom
- Hidden on mobile, shown on desktop

### `AppTopbar`

- 64px tall sticky header (`h-16 sticky top-0`)
- Mobile hamburger menu (shows/hides sidebar)
- Search bar (desktop only, currently non-functional)
- Theme toggle, notifications bell, user avatar/name
- Uses `useUser()` hook to display profile name

### `MarketingHeader` / `MarketingFooter`

Used by the landing page layout. Standard marketing site header and footer.

## Onboarding Components (`src/components/onboarding/`)

### `ProgressHeader`

```tsx
<ProgressHeader currentStep={0} />
```

Shows:
- Step number (zero-padded: "Step 01")
- Step title from `src/config/onboarding-steps.ts`
- Percentage complete
- Animated progress bar
