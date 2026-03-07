import { MaterialIcon } from "@/components/shared/material-icon";

export default function InsightsPage() {
  return (
    <div className="p-4 md:p-8 max-w-7xl mx-auto w-full">
      <h1 className="text-3xl font-black tracking-tight mb-2">Insights</h1>
      <p className="text-slate-500 dark:text-slate-400 mb-12">
        Your learning analytics and performance metrics.
      </p>

      <div className="flex flex-col items-center justify-center py-20 text-center">
        <div className="size-16 rounded-2xl bg-primary/10 text-primary flex items-center justify-center mb-6">
          <MaterialIcon name="analytics" className="text-3xl" />
        </div>
        <h3 className="text-xl font-bold mb-2">Analytics coming soon</h3>
        <p className="text-sm text-slate-500 max-w-sm">
          Learning insights and progress analytics will appear here as you
          complete lessons.
        </p>
      </div>
    </div>
  );
}
