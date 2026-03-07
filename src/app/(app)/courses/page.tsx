import { MaterialIcon } from "@/components/shared/material-icon";

export default function CoursesPage() {
  return (
    <div className="p-4 md:p-8 max-w-7xl mx-auto w-full">
      <h1 className="text-3xl font-black tracking-tight mb-2">My Courses</h1>
      <p className="text-slate-500 dark:text-slate-400 mb-12">
        Your AI-generated courses will appear here.
      </p>

      <div className="flex flex-col items-center justify-center py-20 text-center">
        <div className="size-16 rounded-2xl bg-primary/10 text-primary flex items-center justify-center mb-6">
          <MaterialIcon name="auto_stories" className="text-3xl" />
        </div>
        <h3 className="text-xl font-bold mb-2">No courses yet</h3>
        <p className="text-sm text-slate-500 max-w-sm">
          Once your AI agents finish building your curriculum, your courses will
          appear here.
        </p>
      </div>
    </div>
  );
}
