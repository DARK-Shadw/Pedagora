"use client";

import { MaterialIcon } from "@/components/shared/material-icon";
import { ThemeToggle } from "@/components/shared/theme-toggle";
import { useUser } from "@/hooks/use-user";

interface AppTopbarProps {
  onMenuClick?: () => void;
}

export function AppTopbar({ onMenuClick }: AppTopbarProps) {
  const { profile } = useUser();

  return (
    <header className="h-16 border-b border-slate-200 dark:border-border-dark bg-white/50 dark:bg-[var(--background)]/50 backdrop-blur-md flex items-center justify-between px-4 md:px-8 sticky top-0 z-10">
      {/* Mobile menu button */}
      <button
        onClick={onMenuClick}
        className="md:hidden flex items-center justify-center size-10 rounded-lg hover:bg-slate-100 dark:hover:bg-card-dark"
      >
        <MaterialIcon name="menu" />
      </button>

      {/* Search */}
      <div className="hidden md:flex items-center gap-4 bg-slate-100 dark:bg-card-dark px-4 py-2 rounded-full border border-slate-200 dark:border-border-dark w-96">
        <MaterialIcon name="search" className="text-slate-400 text-xl" />
        <input
          className="bg-transparent border-none focus:ring-0 focus:outline-none text-sm w-full placeholder:text-slate-400"
          placeholder="Search topics, courses, or notes..."
          type="text"
        />
      </div>

      <div className="flex items-center gap-4">
        <ThemeToggle />

        <button className="relative text-slate-500 hover:text-primary transition-colors">
          <MaterialIcon name="notifications" />
          <span className="absolute top-0 right-0 size-2 bg-red-500 rounded-full border-2 border-white dark:border-[var(--background)]" />
        </button>

        <div className="flex items-center gap-3 pl-4 border-l border-slate-200 dark:border-border-dark">
          <div className="flex flex-col items-end">
            <span className="text-sm font-semibold">
              {profile?.name ?? "Learner"}
            </span>
            <span className="text-[10px] text-primary font-bold uppercase tracking-wider">
              Pro Learner
            </span>
          </div>
          <div className="size-10 rounded-full bg-primary/20 flex items-center justify-center ring-2 ring-primary/20">
            <MaterialIcon name="person" className="text-primary text-lg" />
          </div>
        </div>
      </div>
    </header>
  );
}
