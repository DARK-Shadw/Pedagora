# Styling

## Tailwind v4 Setup

Pedagora uses **Tailwind CSS v4** with the new CSS-first configuration. The config lives in `src/app/globals.css`, not a `tailwind.config.js` file.

```css
@import "tailwindcss";
@custom-variant dark (&:is(.dark *));
```

Dark mode is **class-based** — the `dark` class is toggled on `<html>` by `ThemeProvider`. Not using `prefers-color-scheme`.

## Design Tokens

Defined in the `@theme { }` block in `globals.css`:

### Colors

| Token | Value | Usage |
|---|---|---|
| `--color-primary` | `#0d968b` | Brand color, buttons, accents |
| `--color-primary-foreground` | `#ffffff` | Text on primary backgrounds |
| `--color-background-light` | `#fafafa` | Light mode background |
| `--color-background-dark` | `#0D1117` | Dark mode background |
| `--color-card-dark` | `#161b22` | Dark mode card backgrounds |
| `--color-border-dark` | `#30363d` | Dark mode borders |
| `--color-charcoal` | `#1A1A2E` | Foreground text color |

Use via Tailwind classes: `bg-primary`, `text-primary`, `bg-card-dark`, `border-border-dark`.

### Fonts

| Token | Value | Tailwind Class |
|---|---|---|
| `--font-display` | Inter | `font-display` (set on `<body>`) |
| `--font-mono` | JetBrains Mono | `font-mono` |

Inter is loaded via `next/font/google` (optimized, no FOUT). JetBrains Mono and Material Symbols are loaded via Google Fonts CDN.

### CSS Variables (shadcn/ui Convention)

The `:root` and `.dark` blocks define CSS custom properties used by shadcn components:

```css
:root {
  --background: #fafafa;
  --foreground: #1A1A2E;
  --card: #ffffff;
  --primary: #0d968b;
  --destructive: #ef4444;
  --border: #e2e8f0;
  /* etc. */
}

.dark {
  --background: #0D1117;
  --foreground: #e2e8f0;
  --card: #161b22;
  --border: #30363d;
  /* etc. */
}
```

These are referenced via `var(--background)` in Tailwind classes or custom CSS.

## Common Style Patterns

### Card Selection (onboarding)

```tsx
className={`p-4 rounded-xl border transition-all ${
  isSelected
    ? "border-primary ring-1 ring-primary"
    : "border-primary/10 bg-white dark:bg-slate-900"
}`}
```

Active: primary border + ring glow. Inactive: subtle border + white/dark background.

### Technical Labels (monospace uppercase)

```tsx
<span className="technical-label text-[10px] uppercase tracking-widest text-slate-400">
  Step 01
</span>
```

The `.technical-label` class in `globals.css` sets `font-family: var(--font-mono)`.

### Status Indicator (pulsing dot)

```tsx
<span className="relative flex h-2 w-2">
  <span className="animate-ping absolute h-full w-full rounded-full bg-primary opacity-75" />
  <span className="relative rounded-full h-2 w-2 bg-primary" />
</span>
```

### Card Containers

```tsx
// Standard card
className="bg-white dark:bg-card-dark p-6 rounded-xl border border-slate-200 dark:border-border-dark"

// Subtle card (onboarding)
className="p-6 rounded-xl border border-primary/10 bg-white dark:bg-slate-900"
```

### Sticky Headers

```tsx
className="sticky top-0 z-10 bg-white/50 dark:bg-[var(--background)]/50 backdrop-blur-md"
```

The `backdrop-blur-md` with semi-transparent background creates a frosted glass effect.

## Custom CSS Classes

Defined in `globals.css`:

| Class | Purpose |
|---|---|
| `.soft-shadow` | Subtle primary-tinted shadow for elevated elements |
| `.hero-gradient` | Radial gradient for landing page hero section |
| `.custom-scrollbar` | Thin 4px scrollbar with dark track (sidebar) |
| `.technical-label` | Monospace font for technical-looking labels |

## Responsive Design

- Mobile-first approach using Tailwind breakpoints
- Sidebar: hidden on mobile (`-translate-x-full`), shown on desktop (`md:translate-x-0`)
- Topbar: hamburger menu on mobile, search bar on desktop
- Grids: `grid-cols-1` on mobile, `md:grid-cols-2` or `lg:grid-cols-4` on desktop
- Onboarding: fixed `max-w-[640px]` centered layout at all sizes
