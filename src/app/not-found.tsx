import Link from "next/link";
import { Button } from "@/components/ui/button";
import { MaterialIcon } from "@/components/shared/material-icon";

export default function NotFound() {
  return (
    <div className="min-h-screen flex items-center justify-center px-4">
      <div className="text-center space-y-6 max-w-md">
        <div className="size-20 rounded-2xl bg-primary/10 text-primary flex items-center justify-center mx-auto">
          <MaterialIcon name="explore_off" className="text-5xl" />
        </div>
        <h1 className="text-4xl font-black tracking-tight">404</h1>
        <p className="text-slate-500 dark:text-slate-400">
          This page doesn&apos;t exist or has been moved. Let&apos;s get you back on
          track.
        </p>
        <Button asChild>
          <Link href="/">Go Home</Link>
        </Button>
      </div>
    </div>
  );
}
