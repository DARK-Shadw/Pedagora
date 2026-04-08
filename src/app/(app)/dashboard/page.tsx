"use client";

import { useEffect, useState, useCallback } from "react";
import Link from "next/link";
import { MaterialIcon } from "@/components/shared/material-icon";
import { Button } from "@/components/ui/button";
import { useUser } from "@/hooks/use-user";
import { createClient } from "@/lib/supabase/client";

interface ResumeSession {
  session_id: string;
  goal_id: string;
  lesson_id: string;
  goal_title: string;
  last_active_at: string;
}

interface CourseProgress {
  goal_id: string;
  goal_title: string;
  total_lessons: number;
  lessons_ready: number;
}

interface RecentLesson {
  goal_id: string;
  goal_title: string;
  lesson_id: string;
  lesson_title: string;
  animations_ready: number;
  animations_total: number;
}

interface CoursePlanRow {
  goal_id: string;
  total_lessons: number;
  generation_metadata: { lessons_ready?: number } | null;
  course_structure: { modules?: Array<{ lessons?: Array<{ lesson_id: string; title?: string }> }> } | null;
  updated_at: string;
  learning_goals: { title: string };
}

export default function DashboardPage() {
  const { user, profile, loading: userLoading } = useUser();
  const firstName = profile?.name?.split(" ")[0] ?? "Learner";

  const [resumeSession, setResumeSession] = useState<ResumeSession | null>(null);
  const [courseProgress, setCourseProgress] = useState<CourseProgress[]>([]);
  const [recentLessons, setRecentLessons] = useState<RecentLesson[]>([]);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    if (!user) return;
    const sb = createClient();

    // 1. Resume Learning: most recent paused/active teaching session
    const { data: sessionData } = await sb
      .from("teaching_sessions")
      .select(
        `id, goal_id, lesson_id, last_active_at,
         learning_goals!inner(title)`
      )
      .eq("user_id", user.id)
      .in("status", ["active", "paused"])
      .order("last_active_at", { ascending: false })
      .limit(1)
      .maybeSingle();

    if (sessionData) {
      const goal = sessionData.learning_goals as unknown as { title: string };
      setResumeSession({
        session_id: sessionData.id as string,
        goal_id: sessionData.goal_id as string,
        lesson_id: sessionData.lesson_id as string,
        goal_title: goal?.title ?? "Your lesson",
        last_active_at: sessionData.last_active_at as string,
      });
    } else {
      setResumeSession(null);
    }

    // 2. Course progress + recent lessons (single query)
    const { data: planRows } = await sb
      .from("course_plans")
      .select(
        `goal_id, total_lessons, generation_metadata, course_structure,
         updated_at, learning_goals!inner(title)`
      )
      .eq("user_id", user.id)
      .order("updated_at", { ascending: false })
      .limit(5);

    const plans = (planRows ?? []) as unknown as CoursePlanRow[];

    // Top 3 courses by progress display
    setCourseProgress(
      plans.slice(0, 3).map((p) => ({
        goal_id: p.goal_id,
        goal_title: p.learning_goals?.title ?? "Untitled",
        total_lessons: p.total_lessons ?? 0,
        lessons_ready: p.generation_metadata?.lessons_ready ?? 0,
      }))
    );

    // 3. Recent lessons with animation readiness — pull from latest course plan
    if (plans.length > 0) {
      const latest = plans[0];
      const lessonList: { lesson_id: string; lesson_title: string }[] = [];
      const modules = latest.course_structure?.modules ?? [];
      for (const m of modules) {
        for (const l of m.lessons ?? []) {
          lessonList.push({
            lesson_id: l.lesson_id,
            lesson_title: l.title ?? "Untitled lesson",
          });
          if (lessonList.length >= 3) break;
        }
        if (lessonList.length >= 3) break;
      }

      if (lessonList.length > 0) {
        const { data: animsData } = await sb
          .from("lesson_animations")
          .select("lesson_id, status")
          .eq("goal_id", latest.goal_id)
          .in(
            "lesson_id",
            lessonList.map((l) => l.lesson_id)
          );

        const animMap: Record<string, { ready: number; total: number }> = {};
        for (const a of animsData ?? []) {
          const lid = a.lesson_id as string;
          if (!animMap[lid]) animMap[lid] = { ready: 0, total: 0 };
          animMap[lid].total++;
          if (a.status === "completed") animMap[lid].ready++;
        }

        setRecentLessons(
          lessonList.map((l) => {
            const anim = animMap[l.lesson_id] ?? { ready: 0, total: 0 };
            return {
              goal_id: latest.goal_id,
              goal_title: latest.learning_goals?.title ?? "Untitled",
              lesson_id: l.lesson_id,
              lesson_title: l.lesson_title,
              animations_ready: anim.ready,
              animations_total: anim.total,
            };
          })
        );
      } else {
        setRecentLessons([]);
      }
    } else {
      setRecentLessons([]);
    }

    setLoading(false);
  }, [user]);

  useEffect(() => {
    if (userLoading) return;
    if (!user) {
      setLoading(false);
      return;
    }

    load();

    // Realtime: course plans + lesson animations + teaching sessions
    const sb = createClient();
    const channel = sb
      .channel(`dashboard-${user.id}`)
      .on(
        "postgres_changes",
        { event: "*", schema: "public", table: "course_plans", filter: `user_id=eq.${user.id}` },
        () => load()
      )
      .on(
        "postgres_changes",
        { event: "*", schema: "public", table: "lesson_animations", filter: `user_id=eq.${user.id}` },
        () => load()
      )
      .on(
        "postgres_changes",
        { event: "*", schema: "public", table: "teaching_sessions", filter: `user_id=eq.${user.id}` },
        () => load()
      )
      .subscribe();

    return () => {
      sb.removeChannel(channel);
    };
  }, [user, userLoading, load]);

  if (loading || userLoading) {
    return (
      <div className="p-8 max-w-7xl mx-auto w-full animate-pulse space-y-6">
        <div className="h-8 w-72 bg-muted rounded" />
        <div className="h-64 bg-muted rounded-xl" />
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          <div className="h-64 bg-muted rounded-xl" />
          <div className="lg:col-span-2 h-64 bg-muted rounded-xl" />
        </div>
      </div>
    );
  }

  return (
    <div className="p-4 md:p-8 space-y-8 max-w-7xl mx-auto w-full">
      {/* Welcome */}
      <div>
        <h2 className="text-3xl font-black tracking-tight">
          Welcome back, {firstName}
        </h2>
        <p className="text-slate-500 dark:text-slate-400 mt-1">
          {resumeSession
            ? "Pick up where you left off."
            : courseProgress.length > 0
              ? "Your courses are ready. Jump in to start learning."
              : "Create a learning goal to get started."}
        </p>
      </div>

      {/* Resume Learning Hero */}
      <section className="group relative overflow-hidden rounded-xl bg-slate-900 border border-border-dark shadow-2xl">
        <div className="absolute inset-0 opacity-10 pointer-events-none bg-[radial-gradient(circle_at_70%_30%,rgba(13,150,139,0.3),transparent_70%)]" />
        <div className="relative z-10 grid grid-cols-1 md:grid-cols-2 gap-0">
          <div className="p-6 md:p-10 flex flex-col justify-center">
            {resumeSession ? (
              <>
                <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-primary/20 text-primary text-xs font-bold uppercase tracking-widest mb-4 w-fit">
                  <MaterialIcon name="bolt" className="text-sm" />
                  Active Now
                </div>
                <h3 className="text-xl md:text-2xl font-bold text-white mb-2 tracking-tight leading-tight">
                  Resume: {resumeSession.goal_title}
                </h3>
                <p className="text-slate-400 mb-8 max-w-sm">
                  Your last lesson is paused and waiting. Continue where you
                  left off.
                </p>
                <Button className="w-fit" asChild>
                  <Link href={`/classroom/v2/${resumeSession.session_id}`}>
                    Continue Lesson
                    <MaterialIcon name="play_arrow" className="text-lg" />
                  </Link>
                </Button>
              </>
            ) : courseProgress.length > 0 ? (
              <>
                <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-primary/20 text-primary text-xs font-bold uppercase tracking-widest mb-4 w-fit">
                  <MaterialIcon name="auto_awesome" className="text-sm" />
                  Ready to Learn
                </div>
                <h3 className="text-xl md:text-2xl font-bold text-white mb-2 tracking-tight leading-tight">
                  {courseProgress[0].goal_title}
                </h3>
                <p className="text-slate-400 mb-8 max-w-sm">
                  Your AI agents have built your curriculum. Start your first
                  lesson.
                </p>
                <Button className="w-fit" asChild>
                  <Link href={`/courses/${courseProgress[0].goal_id}`}>
                    View Course
                    <MaterialIcon name="arrow_forward" className="text-lg" />
                  </Link>
                </Button>
              </>
            ) : (
              <>
                <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-primary/20 text-primary text-xs font-bold uppercase tracking-widest mb-4 w-fit">
                  <MaterialIcon name="rocket_launch" className="text-sm" />
                  Get Started
                </div>
                <h3 className="text-xl md:text-2xl font-bold text-white mb-2 tracking-tight leading-tight">
                  Start your first learning goal
                </h3>
                <p className="text-slate-400 mb-8 max-w-sm">
                  Tell us what you want to learn and our AI agents will build a
                  full course tailored to you.
                </p>
                <Button className="w-fit" asChild>
                  <Link href="/onboarding/goal">
                    Create a Goal
                    <MaterialIcon name="arrow_forward" className="text-lg" />
                  </Link>
                </Button>
              </>
            )}
          </div>
          <div className="hidden md:flex relative h-full min-h-[300px] overflow-hidden items-center justify-center">
            <div className="absolute inset-0 bg-gradient-to-r from-slate-900 via-transparent to-transparent z-10" />
            <div className="absolute inset-0 bg-gradient-to-br from-primary/10 via-slate-900 to-slate-800" />
            <MaterialIcon
              name="hub"
              className="text-[120px] text-primary/20 relative z-0"
            />
          </div>
        </div>
      </section>

      {/* Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left column */}
        <div className="lg:col-span-1 flex flex-col gap-6">
          {/* Progress Tracking */}
          <div className="bg-white dark:bg-card-dark p-6 rounded-xl border border-slate-200 dark:border-border-dark flex flex-col">
            <div className="flex items-center justify-between mb-6">
              <h4 className="font-bold">Course Progress</h4>
              <MaterialIcon name="trending_up" className="text-slate-400" />
            </div>
            {courseProgress.length > 0 ? (
              <div className="space-y-6">
                {courseProgress.map((c) => {
                  const pct =
                    c.total_lessons > 0
                      ? Math.round((100 * c.lessons_ready) / c.total_lessons)
                      : 0;
                  return (
                    <Link
                      href={`/courses/${c.goal_id}`}
                      key={c.goal_id}
                      className="block group"
                    >
                      <div className="flex justify-between items-center mb-2">
                        <span className="text-xs font-medium text-slate-500 dark:text-slate-400 truncate group-hover:text-primary transition-colors">
                          {c.goal_title}
                        </span>
                        <span className="text-xs font-bold shrink-0 ml-2">
                          {pct}%
                        </span>
                      </div>
                      <div className="w-full bg-slate-100 dark:bg-border-dark rounded-full h-1.5">
                        <div
                          className="bg-primary h-full rounded-full transition-all"
                          style={{ width: `${pct}%` }}
                        />
                      </div>
                    </Link>
                  );
                })}
              </div>
            ) : (
              <p className="text-sm text-slate-500">
                No courses yet. Create a goal to get started.
              </p>
            )}
            <Button variant="outline" className="mt-8 w-full" asChild>
              <Link href="/courses">View All Courses</Link>
            </Button>
          </div>

          {/* Tip */}
          <div className="bg-primary/5 dark:bg-primary/10 p-6 rounded-xl border border-primary/20 flex flex-col gap-4">
            <h4 className="font-bold text-primary flex items-center gap-2">
              <MaterialIcon name="lightbulb" className="text-lg" />
              Tip
            </h4>
            <p className="text-sm text-slate-600 dark:text-slate-300 leading-relaxed italic">
              Your AI teacher controls every visual frame in real time. Ask
              questions during the lesson — Pedagora will pause and explain.
            </p>
          </div>
        </div>

        {/* Right column — Recently Generated Lessons */}
        <div className="lg:col-span-2 space-y-6">
          <div className="bg-white dark:bg-card-dark p-6 rounded-xl border border-slate-200 dark:border-border-dark">
            <div className="flex items-center justify-between mb-6">
              <h4 className="font-bold">Recently Generated Lessons</h4>
              <Link
                href="/courses"
                className="text-xs font-bold text-primary hover:underline"
              >
                See All
              </Link>
            </div>
            {recentLessons.length > 0 ? (
              <div className="space-y-3">
                {recentLessons.map((lesson) => {
                  const isReady = lesson.animations_ready > 0;
                  const animPct = lesson.animations_total
                    ? Math.round(
                        (100 * lesson.animations_ready) /
                          lesson.animations_total
                      )
                    : 0;
                  return (
                    <Link
                      key={`${lesson.goal_id}-${lesson.lesson_id}`}
                      href={`/courses/${lesson.goal_id}`}
                      className="flex items-center gap-4 p-4 rounded-lg bg-slate-50 dark:bg-[var(--background)] border border-slate-100 dark:border-border-dark hover:border-primary/30 transition-colors"
                    >
                      <div
                        className={`size-12 rounded-lg flex items-center justify-center shrink-0 ${
                          isReady
                            ? "bg-primary/10 text-primary"
                            : "bg-amber-500/10 text-amber-500"
                        }`}
                      >
                        <MaterialIcon
                          name={isReady ? "play_circle" : "hourglass_empty"}
                        />
                      </div>
                      <div className="flex-1 min-w-0">
                        <h5 className="text-sm font-bold truncate">
                          {lesson.lesson_title}
                        </h5>
                        <p className="text-xs text-slate-500 dark:text-slate-400 truncate">
                          {lesson.goal_title} ·{" "}
                          {lesson.animations_total > 0 ? (
                            <span
                              className={
                                isReady ? "text-primary" : "text-amber-500"
                              }
                            >
                              {lesson.animations_ready}/
                              {lesson.animations_total} animations ({animPct}%)
                            </span>
                          ) : (
                            <span className="text-amber-500">Queued</span>
                          )}
                        </p>
                      </div>
                      <MaterialIcon
                        name="arrow_forward"
                        className="text-primary"
                      />
                    </Link>
                  );
                })}
              </div>
            ) : (
              <div className="text-center py-12">
                <p className="text-sm text-slate-500 mb-4">
                  No lessons generated yet.
                </p>
                <Button asChild>
                  <Link href="/onboarding/goal">Create your first goal</Link>
                </Button>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
