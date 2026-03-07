"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { cn } from "@/lib/utils";
import { Logo } from "@/components/shared/logo";
import { MaterialIcon } from "@/components/shared/material-icon";
import { Button } from "@/components/ui/button";
import { useOnboardingStore } from "@/stores/onboarding-store";
import { appNav, appNavSupport } from "@/config/navigation";

interface AppSidebarProps {
  className?: string;
}

export function AppSidebar({ className }: AppSidebarProps) {
  const pathname = usePathname();
  const router = useRouter();
  const resetOnboarding = useOnboardingStore((s) => s.reset);

  return (
    <aside
      className={cn(
        "w-64 border-r border-slate-200 dark:border-border-dark flex flex-col bg-white dark:bg-[var(--background)] h-full shrink-0",
        className
      )}
    >
      {/* Logo */}
      <div className="p-6 flex items-center gap-3">
        <Logo />
        <div className="flex flex-col ml-[-4px]">
          <p className="text-slate-500 dark:text-primary text-xs font-medium uppercase tracking-widest">
            AI Academy
          </p>
        </div>
      </div>

      {/* Navigation */}
      <nav className="flex-1 px-4 space-y-1 mt-4 custom-scrollbar overflow-y-auto">
        {appNav.map((item) => {
          const isActive = pathname.startsWith(item.href);
          return (
            <Link
              key={item.href}
              href={item.href}
              className={cn(
                "flex items-center gap-3 px-3 py-2.5 rounded-lg transition-colors",
                isActive
                  ? "bg-primary/10 text-primary font-medium"
                  : "text-slate-600 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-card-dark"
              )}
            >
              <MaterialIcon name={item.icon} className="text-[22px]" />
              <span className="text-sm">{item.label}</span>
            </Link>
          );
        })}

        <div className="pt-6 pb-2 px-3 text-[10px] font-bold text-slate-400 uppercase tracking-widest">
          Support
        </div>

        {appNavSupport.map((item) => {
          const isActive = pathname.startsWith(item.href);
          return (
            <Link
              key={item.href}
              href={item.href}
              className={cn(
                "flex items-center gap-3 px-3 py-2.5 rounded-lg transition-colors",
                isActive
                  ? "bg-primary/10 text-primary font-medium"
                  : "text-slate-600 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-card-dark"
              )}
            >
              <MaterialIcon name={item.icon} className="text-[22px]" />
              <span className="text-sm">{item.label}</span>
            </Link>
          );
        })}
      </nav>

      {/* Bottom CTA */}
      <div className="p-4 mt-auto border-t border-slate-200 dark:border-border-dark">
        <Button
          className="w-full h-11"
          onClick={() => {
            resetOnboarding();
            router.push("/onboarding/goal");
          }}
        >
          <MaterialIcon name="add_circle" className="text-lg" />
          <span className="text-sm font-semibold">New Inquiry</span>
        </Button>
      </div>
    </aside>
  );
}
