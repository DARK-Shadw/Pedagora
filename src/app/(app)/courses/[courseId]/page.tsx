"use client";

import { useEffect, useState, useCallback } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import { createClient } from "@/lib/supabase/client";
import { useUser } from "@/hooks/use-user";
import { Button } from "@/components/ui/button";
import { MaterialIcon } from "@/components/shared/material-icon";

interface LessonView {
  lesson_id: string;
  title: string;
  estimated_minutes: number;
  total_frames: number;
  animations_ready: number;
  animations_total: number;
  has_planner_frames: boolean;
}

interface ModuleView {
  module_id: string;
  title: string;
  lessons: LessonView[];
}

interface StructureLesson {
  lesson_id: string;
  title?: string;
  estimated_minutes?: number;
}

interface StructureModule {
  module_id?: string;
  title?: string;
  lessons?: StructureLesson[];
}

interface CourseStructure {
  modules?: StructureModule[];
}

interface LessonPlanDetail {
  total_frames?: number;
  frames?: unknown[];
  error?: string;
}

interface AnimationRow {
  lesson_id: string;
  animation_id: string;
  status: string;
}

export default function CourseDetailPage() {
  const params = useParams();
  const router = useRouter();
  const { user, loading: userLoading } = useUser();
  const goalId = params.courseId as string;

  const [courseTitle, setCourseTitle] = useState("");
  const [modules, setModules] = useState<ModuleView[]>([]);
  const [loading, setLoading] = useState(true);
  const [notFound, setNotFound] = useState(false);
  const [startingLessonId, setStartingLessonId] = useState<string | null>(null);
  const [generatingLessonId, setGeneratingLessonId] = useState<string | null>(null);
  const [startError, setStartError] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!user || !goalId) return;
    const sb = createClient();

    // Fetch course plan + goal title
    const { data: planRow, error: planErr } = await sb
      .from("course_plans")
      .select(
        `course_structure, lesson_plans, learning_goals!inner(title)`
      )
      .eq("goal_id", goalId)
      .eq("user_id", user.id)
      .maybeSingle();

    if (planErr || !planRow) {
      setNotFound(true);
      setLoading(false);
      return;
    }

    const goal = planRow.learning_goals as unknown as { title: string };
    setCourseTitle(goal?.title ?? "Untitled course");

    // Fetch animation status for all lessons
    const { data: animsData } = await sb
      .from("lesson_animations")
      .select("lesson_id, animation_id, status")
      .eq("goal_id", goalId);

    const anims = (animsData ?? []) as AnimationRow[];
    const animMap: Record<string, { ready: number; total: number }> = {};
    for (const a of anims) {
      if (!animMap[a.lesson_id]) animMap[a.lesson_id] = { ready: 0, total: 0 };
      animMap[a.lesson_id].total++;
      if (a.status === "completed") animMap[a.lesson_id].ready++;
    }

    const structure = (planRow.course_structure ?? {}) as CourseStructure;
    const lessonPlans = (planRow.lesson_plans ?? {}) as Record<
      string,
      LessonPlanDetail
    >;

    const built: ModuleView[] = (structure.modules ?? []).map((m, mi) => ({
      module_id: m.module_id ?? `mod-${mi}`,
      title: m.title ?? `Module ${mi + 1}`,
      lessons: (m.lessons ?? []).map((l) => {
        const detail = lessonPlans[l.lesson_id] ?? {};
        const anim = animMap[l.lesson_id] ?? { ready: 0, total: 0 };
        const totalFrames = detail.total_frames ?? 0;
        return {
          lesson_id: l.lesson_id,
          title: l.title ?? "Untitled lesson",
          estimated_minutes: l.estimated_minutes ?? 30,
          total_frames: totalFrames,
          animations_ready: anim.ready,
          animations_total: anim.total || totalFrames,
          has_planner_frames: totalFrames > 0 && !detail.error,
        };
      }),
    }));

    setModules(built);
    setLoading(false);
  }, [user, goalId]);

  useEffect(() => {
    if (userLoading) return;
    if (!user) {
      setLoading(false);
      return;
    }

    load();

    const sb = createClient();
    const animChannel = sb
      .channel(`anims-${goalId}`)
      .on(
        "postgres_changes",
        {
          event: "*",
          schema: "public",
          table: "lesson_animations",
          filter: `goal_id=eq.${goalId}`,
        },
        () => {
          load();
        }
      )
      .subscribe();

    const planChannel = sb
      .channel(`plan-${goalId}`)
      .on(
        "postgres_changes",
        {
          event: "*",
          schema: "public",
          table: "course_plans",
          filter: `goal_id=eq.${goalId}`,
        },
        () => {
          load();
        }
      )
      .subscribe();

    return () => {
      sb.removeChannel(animChannel);
      sb.removeChannel(planChannel);
    };
  }, [user, userLoading, goalId, load]);

  async function startLesson(lessonId: string) {
    if (!user) return;
    setStartingLessonId(lessonId);
    setStartError(null);

    const sb = createClient();
    const { data: sessionData } = await sb.auth.getSession();
    if (!sessionData.session?.access_token) {
      setStartError("Not authenticated. Please refresh and sign in again.");
      setStartingLessonId(null);
      return;
    }

    try {
      const res = await fetch(
        `${process.env.NEXT_PUBLIC_BACKEND_URL}/teacher/sessions`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${sessionData.session.access_token}`,
          },
          body: JSON.stringify({ goal_id: goalId, lesson_id: lessonId }),
        }
      );

      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || "Failed to start session");
      }

      const data = await res.json();
      router.push(`/classroom/v2/${data.session_id}`);
    } catch (e) {
      console.error("[CourseDetail] startLesson failed:", e);
      setStartError(
        e instanceof Error ? e.message : "Failed to start lesson. Try again."
      );
      setStartingLessonId(null);
    }
  }

  async function generateAnimations(lessonId: string) {
    if (!user) return;
    setGeneratingLessonId(lessonId);
    setStartError(null);

    const sb = createClient();
    const { data: sessionData } = await sb.auth.getSession();
    if (!sessionData.session?.access_token) {
      setStartError("Not authenticated. Please refresh and sign in again.");
      setGeneratingLessonId(null);
      return;
    }

    try {
      const res = await fetch(
        `${process.env.NEXT_PUBLIC_BACKEND_URL}/agents/animate-lesson`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${sessionData.session.access_token}`,
          },
          body: JSON.stringify({ goal_id: goalId, lesson_id: lessonId }),
        }
      );

      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || "Failed to start animation generation");
      }
      // Existing realtime subscriptions on lesson_animations will
      // auto-refresh the UI as animations complete — no polling needed.
    } catch (e) {
      console.error("[CourseDetail] generateAnimations failed:", e);
      setStartError(
        e instanceof Error ? e.message : "Failed to generate. Try again."
      );
    } finally {
      setGeneratingLessonId(null);
    }
  }

  if (loading || userLoading) {
    return (
      <div className="p-8 max-w-5xl mx-auto w-full animate-pulse">
        <div className="h-8 w-72 bg-muted rounded mb-8" />
        <div className="space-y-4">
          {[1, 2, 3].map((i) => (
            <div key={i} className="h-32 bg-muted rounded-xl" />
          ))}
        </div>
      </div>
    );
  }

  if (notFound) {
    return (
      <div className="p-4 md:p-8 max-w-5xl mx-auto w-full">
        <Link
          href="/courses"
          className="text-sm text-primary font-bold inline-flex items-center gap-1 mb-6"
        >
          <MaterialIcon name="arrow_back" className="text-base" />
          All courses
        </Link>
        <div className="flex flex-col items-center justify-center py-20 text-center">
          <div className="size-16 rounded-2xl bg-amber-500/10 text-amber-500 flex items-center justify-center mb-6">
            <MaterialIcon name="search_off" className="text-3xl" />
          </div>
          <h3 className="text-xl font-bold mb-2">Course not found</h3>
          <p className="text-sm text-slate-500 max-w-sm">
            This course doesn&apos;t exist yet, or you don&apos;t have access to
            it.
          </p>
        </div>
      </div>
    );
  }

  const totalLessons = modules.reduce((acc, m) => acc + m.lessons.length, 0);
  const readyLessons = modules.reduce(
    (acc, m) => acc + m.lessons.filter((l) => l.animations_ready > 0).length,
    0
  );

  return (
    <div className="p-4 md:p-8 max-w-5xl mx-auto w-full">
      <Link
        href="/courses"
        className="text-sm text-primary font-bold inline-flex items-center gap-1 mb-6 hover:underline"
      >
        <MaterialIcon name="arrow_back" className="text-base" />
        All courses
      </Link>

      <h1 className="text-3xl md:text-4xl font-black tracking-tight mb-2">
        {courseTitle}
      </h1>
      <p className="text-slate-500 dark:text-slate-400 mb-8">
        {modules.length} modules · {totalLessons} lessons ·{" "}
        <span className="text-primary font-medium">
          {readyLessons} ready to start
        </span>
      </p>

      {startError && (
        <div className="mb-6 flex items-center gap-2 text-sm text-destructive bg-destructive/10 p-3 rounded-lg">
          <MaterialIcon name="error" className="text-lg" />
          {startError}
        </div>
      )}

      <div className="space-y-6">
        {modules.map((mod, mi) => (
          <div
            key={mod.module_id}
            className="border border-primary/10 rounded-xl bg-white dark:bg-slate-900 p-6"
          >
            <div className="flex items-center gap-3 mb-6">
              <span className="text-[10px] font-bold text-primary uppercase tracking-widest">
                Module {mi + 1}
              </span>
              <h2 className="text-xl font-bold">{mod.title}</h2>
            </div>

            <div className="space-y-3">
              {mod.lessons.map((lesson) => {
                const isReady = lesson.animations_ready > 0;
                const isStarting = startingLessonId === lesson.lesson_id;
                const isGenerating = generatingLessonId === lesson.lesson_id;
                const isInProgress =
                  lesson.animations_total > 0 &&
                  lesson.animations_ready < lesson.animations_total;
                const canGenerate =
                  lesson.has_planner_frames &&
                  lesson.animations_total === 0 &&
                  !isGenerating;
                const animPct = lesson.animations_total
                  ? Math.round(
                      (100 * lesson.animations_ready) / lesson.animations_total
                    )
                  : 0;
                const statusText = !lesson.has_planner_frames
                  ? "Planning..."
                  : lesson.animations_total === 0
                    ? "Ready to generate"
                    : `${lesson.animations_ready}/${lesson.animations_total} animations ready (${animPct}%)`;

                return (
                  <div
                    key={lesson.lesson_id}
                    className="flex flex-col md:flex-row md:items-center justify-between gap-4 p-4 rounded-lg bg-slate-50 dark:bg-slate-800/50 border border-slate-100 dark:border-slate-700"
                  >
                    <div className="flex-1 min-w-0">
                      <h3 className="font-bold text-sm mb-1">{lesson.title}</h3>
                      <p className="text-xs text-slate-500">
                        {lesson.estimated_minutes} min ·{" "}
                        {lesson.total_frames > 0 && (
                          <>{lesson.total_frames} frames · </>
                        )}
                        <span
                          className={isReady ? "text-primary" : "text-amber-500"}
                        >
                          {statusText}
                        </span>
                      </p>
                      {isInProgress && (
                        <div className="mt-2 h-1 w-full max-w-xs bg-slate-200 dark:bg-slate-700 rounded-full overflow-hidden">
                          <div
                            className="h-full bg-amber-500 rounded-full transition-all"
                            style={{ width: `${animPct}%` }}
                          />
                        </div>
                      )}
                    </div>
                    <div className="flex gap-2 shrink-0">
                      {canGenerate && (
                        <Button
                          onClick={() => generateAnimations(lesson.lesson_id)}
                          size="sm"
                          variant="outline"
                        >
                          <MaterialIcon name="auto_awesome" className="text-base" />
                          Generate
                        </Button>
                      )}
                      {isGenerating && (
                        <Button size="sm" variant="outline" disabled>
                          <MaterialIcon name="hourglass_top" className="text-base" />
                          Starting...
                        </Button>
                      )}
                      {isInProgress && (
                        <Button size="sm" variant="outline" disabled>
                          <MaterialIcon name="hourglass_top" className="text-base" />
                          {animPct}%
                        </Button>
                      )}
                      <Button
                        onClick={() => startLesson(lesson.lesson_id)}
                        disabled={!isReady || isStarting}
                        size="sm"
                      >
                        {isStarting ? (
                          <>Starting...</>
                        ) : isReady ? (
                          <>
                            Start Lesson
                            <MaterialIcon name="play_arrow" className="text-base" />
                          </>
                        ) : (
                          <>Not Ready</>
                        )}
                      </Button>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
