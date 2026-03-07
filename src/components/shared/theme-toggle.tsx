"use client";

import { useThemeStore } from "@/stores/theme-store";
import { MaterialIcon } from "./material-icon";

export function ThemeToggle() {
  const { theme, setTheme } = useThemeStore();

  const next = theme === "dark" ? "light" : "dark";

  return (
    <button
      onClick={() => setTheme(next)}
      className="flex items-center justify-center size-9 rounded-lg text-slate-500 hover:text-primary hover:bg-primary/10 transition-colors"
      aria-label={`Switch to ${next} mode`}
    >
      <MaterialIcon
        name={theme === "dark" ? "light_mode" : "dark_mode"}
        className="text-xl"
      />
    </button>
  );
}
