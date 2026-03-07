"use client";

import { Button } from "@/components/ui/button";
import { MaterialIcon } from "@/components/shared/material-icon";

export default function Error({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <div className="min-h-screen flex items-center justify-center px-4">
      <div className="text-center space-y-6 max-w-md">
        <div className="size-20 rounded-2xl bg-destructive/10 text-destructive flex items-center justify-center mx-auto">
          <MaterialIcon name="error_outline" className="text-5xl" />
        </div>
        <h1 className="text-3xl font-black tracking-tight">
          Something went wrong
        </h1>
        <p className="text-slate-500 dark:text-slate-400">
          {error.message || "An unexpected error occurred. Please try again."}
        </p>
        <Button onClick={reset}>Try Again</Button>
      </div>
    </div>
  );
}
