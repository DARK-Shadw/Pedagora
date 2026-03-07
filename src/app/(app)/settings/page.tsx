"use client";

import { useUser } from "@/hooks/use-user";
import { Button } from "@/components/ui/button";
import { MaterialIcon } from "@/components/shared/material-icon";
import { ThemeToggle } from "@/components/shared/theme-toggle";
import { createClient } from "@/lib/supabase/client";
import { useRouter } from "next/navigation";

export default function SettingsPage() {
  const { profile } = useUser();
  const router = useRouter();

  async function handleSignOut() {
    const supabase = createClient();
    await supabase.auth.signOut();
    router.push("/");
    router.refresh();
  }

  return (
    <div className="p-4 md:p-8 max-w-3xl mx-auto w-full space-y-8">
      <div>
        <h1 className="text-3xl font-black tracking-tight mb-2">Settings</h1>
        <p className="text-slate-500 dark:text-slate-400">
          Manage your account and preferences.
        </p>
      </div>

      {/* Profile section */}
      <div className="bg-white dark:bg-card-dark p-6 rounded-xl border border-slate-200 dark:border-border-dark space-y-4">
        <h3 className="font-bold flex items-center gap-2">
          <MaterialIcon name="person" className="text-primary" />
          Profile
        </h3>
        <div className="grid grid-cols-2 gap-4 text-sm">
          <div>
            <p className="text-slate-500">Name</p>
            <p className="font-medium">{profile?.name ?? "—"}</p>
          </div>
          <div>
            <p className="text-slate-500">Email</p>
            <p className="font-medium">{profile?.email ?? "—"}</p>
          </div>
        </div>
      </div>

      {/* Theme section */}
      <div className="bg-white dark:bg-card-dark p-6 rounded-xl border border-slate-200 dark:border-border-dark space-y-4">
        <h3 className="font-bold flex items-center gap-2">
          <MaterialIcon name="palette" className="text-primary" />
          Appearance
        </h3>
        <div className="flex items-center justify-between">
          <p className="text-sm">Toggle dark/light mode</p>
          <ThemeToggle />
        </div>
      </div>

      {/* Sign out */}
      <Button variant="outline" onClick={handleSignOut} className="w-full">
        <MaterialIcon name="logout" className="text-lg" />
        Sign Out
      </Button>
    </div>
  );
}
