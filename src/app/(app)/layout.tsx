"use client";

import { useState } from "react";
import { AppSidebar } from "@/components/layout/app-sidebar";
import { AppTopbar } from "@/components/layout/app-topbar";
import { cn } from "@/lib/utils";

export default function AppLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const [sidebarOpen, setSidebarOpen] = useState(false);

  return (
    <div className="relative flex h-screen w-full overflow-hidden">
      {/* Mobile overlay */}
      {sidebarOpen && (
        <div
          className="fixed inset-0 z-40 bg-black/50 md:hidden"
          onClick={() => setSidebarOpen(false)}
        />
      )}

      {/* Sidebar - hidden on mobile, shown on desktop */}
      <div
        className={cn(
          "fixed inset-y-0 left-0 z-50 md:relative md:z-auto transition-transform duration-200",
          sidebarOpen ? "translate-x-0" : "-translate-x-full md:translate-x-0"
        )}
      >
        <AppSidebar />
      </div>

      {/* Main content */}
      <main className="flex-1 h-screen overflow-y-auto custom-scrollbar flex flex-col">
        <AppTopbar onMenuClick={() => setSidebarOpen(!sidebarOpen)} />
        <div className="flex-1">{children}</div>
        <div className="mt-auto py-8 text-center text-slate-500 dark:text-slate-600 text-xs">
          &copy; {new Date().getFullYear()} Pedagora AI Learning Platform. All
          rights reserved.
        </div>
      </main>
    </div>
  );
}
