import { MaterialIcon } from "@/components/shared/material-icon";

export default function SessionsPage() {
  return (
    <div className="p-4 md:p-8 max-w-7xl mx-auto w-full">
      <h1 className="text-3xl font-black tracking-tight mb-2">Sessions</h1>
      <p className="text-slate-500 dark:text-slate-400 mb-12">
        Your scheduled and past learning sessions.
      </p>

      <div className="flex flex-col items-center justify-center py-20 text-center">
        <div className="size-16 rounded-2xl bg-primary/10 text-primary flex items-center justify-center mb-6">
          <MaterialIcon name="event_repeat" className="text-3xl" />
        </div>
        <h3 className="text-xl font-bold mb-2">No sessions scheduled</h3>
        <p className="text-sm text-slate-500 max-w-sm">
          Sessions will be automatically scheduled once your course is ready.
        </p>
      </div>
    </div>
  );
}
