"use client";

import { MaterialIcon } from "@/components/shared/material-icon";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { useUser } from "@/hooks/use-user";
import Link from "next/link";

const progressItems = [
  { name: "Advanced Machine Learning", progress: 65, color: "bg-primary" },
  { name: "Natural Language Processing", progress: 22, color: "bg-blue-400" },
  { name: "Data Visualization", progress: 91, color: "bg-amber-400" },
];

const upcomingSessions = [
  {
    month: "MAR",
    day: "10",
    title: "1-on-1 AI Mentorship",
    subtitle: "With Dr. Julian Thorne",
    time: "10:00 AM EST",
    icon: "video_call",
    active: true,
  },
  {
    month: "MAR",
    day: "12",
    title: "Workshop: Transformers 101",
    subtitle: "Group Session",
    time: "2:30 PM EST",
    icon: "notifications_active",
    active: false,
  },
];

const recommended = [
  {
    icon: "psychology",
    iconColor: "bg-indigo-500/10 text-indigo-500",
    title: "Attention Mechanisms",
    desc: "Deep dive into self-attention and cross-attention in modern LLMs.",
    duration: "45 MINS",
  },
  {
    icon: "database",
    iconColor: "bg-emerald-500/10 text-emerald-500",
    title: "Vector Databases",
    desc: "How to store and retrieve high-dimensional embeddings efficiently.",
    duration: "30 MINS",
  },
];

export default function DashboardPage() {
  const { profile } = useUser();
  const firstName = profile?.name?.split(" ")[0] ?? "Learner";

  return (
    <div className="p-4 md:p-8 space-y-8 max-w-7xl mx-auto w-full">
      {/* Welcome */}
      <div>
        <h2 className="text-3xl font-black tracking-tight">
          Welcome back, {firstName}
        </h2>
        <p className="text-slate-500 dark:text-slate-400 mt-1">
          You&apos;ve completed 75% of your weekly goals. Keep the momentum!
        </p>
      </div>

      {/* Resume Learning Hero */}
      <section className="group relative overflow-hidden rounded-xl bg-slate-900 border border-border-dark shadow-2xl">
        <div className="absolute inset-0 opacity-10 pointer-events-none bg-[radial-gradient(circle_at_70%_30%,rgba(13,150,139,0.3),transparent_70%)]" />
        <div className="relative z-10 grid grid-cols-1 md:grid-cols-2 gap-0">
          <div className="p-6 md:p-10 flex flex-col justify-center">
            <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-primary/20 text-primary text-xs font-bold uppercase tracking-widest mb-4 w-fit">
              <MaterialIcon name="bolt" className="text-sm" />
              Active Now
            </div>
            <h3 className="text-xl md:text-2xl font-bold text-white mb-2 tracking-tight leading-tight">
              Resume Learning: Neural Networks
            </h3>
            <p className="text-slate-400 mb-8 max-w-sm">
              Module 4: Backpropagation and Gradient Descent. You&apos;re almost
              there!
            </p>
            <div className="flex flex-col gap-4 mb-8">
              <div className="flex justify-between text-xs font-semibold uppercase tracking-wider text-slate-500">
                <span>Progress</span>
                <span className="text-primary">75%</span>
              </div>
              <div className="w-full bg-slate-800 rounded-full h-1.5">
                <div
                  className="bg-primary h-full rounded-full transition-all"
                  style={{ width: "75%" }}
                />
              </div>
            </div>
            <Button className="w-fit" asChild>
              <Link href="/courses">
                Continue Lesson
                <MaterialIcon name="arrow_forward" className="text-lg" />
              </Link>
            </Button>
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
              <h4 className="font-bold">Progress Tracking</h4>
              <MaterialIcon name="trending_up" className="text-slate-400" />
            </div>
            <div className="space-y-6">
              {progressItems.map((item) => (
                <div key={item.name}>
                  <div className="flex justify-between items-center mb-2">
                    <span className="text-xs font-medium text-slate-500 dark:text-slate-400">
                      {item.name}
                    </span>
                    <span className="text-xs font-bold">{item.progress}%</span>
                  </div>
                  <div className="w-full bg-slate-100 dark:bg-border-dark rounded-full h-1.5">
                    <div
                      className={`${item.color} h-full rounded-full transition-all`}
                      style={{ width: `${item.progress}%` }}
                    />
                  </div>
                </div>
              ))}
            </div>
            <Button variant="outline" className="mt-8 w-full" asChild>
              <Link href="/insights">View Full Analytics</Link>
            </Button>
          </div>

          {/* Weekly Tip */}
          <div className="bg-primary/5 dark:bg-primary/10 p-6 rounded-xl border border-primary/20 flex flex-col gap-4">
            <h4 className="font-bold text-primary flex items-center gap-2">
              <MaterialIcon name="lightbulb" className="text-lg" />
              Weekly Tip
            </h4>
            <p className="text-sm text-slate-600 dark:text-slate-300 leading-relaxed italic">
              &quot;Spaced repetition for Neural Network architecture
              memorization is 3x more effective than cramming.&quot;
            </p>
          </div>
        </div>

        {/* Right column */}
        <div className="lg:col-span-2 space-y-6">
          {/* Upcoming Sessions */}
          <div className="bg-white dark:bg-card-dark p-6 rounded-xl border border-slate-200 dark:border-border-dark">
            <div className="flex items-center justify-between mb-6">
              <h4 className="font-bold">Upcoming Sessions</h4>
              <Link
                href="/sessions"
                className="text-xs font-bold text-primary hover:underline"
              >
                See Calendar
              </Link>
            </div>
            <div className="space-y-4">
              {upcomingSessions.map((session) => (
                <div
                  key={session.title}
                  className={`flex items-center gap-4 p-4 rounded-lg bg-slate-50 dark:bg-[var(--background)] border border-slate-100 dark:border-border-dark ${
                    !session.active ? "opacity-75" : ""
                  }`}
                >
                  <div className="flex flex-col items-center justify-center size-12 bg-white dark:bg-card-dark rounded-lg border border-slate-200 dark:border-border-dark shrink-0">
                    <span
                      className={`text-xs font-black ${session.active ? "text-primary" : "text-slate-400"}`}
                    >
                      {session.month}
                    </span>
                    <span className="text-lg font-bold leading-none">
                      {session.day}
                    </span>
                  </div>
                  <div className="flex-1">
                    <h5 className="text-sm font-bold">{session.title}</h5>
                    <p className="text-xs text-slate-500 dark:text-slate-400">
                      {session.subtitle} &bull; {session.time}
                    </p>
                  </div>
                  <button className="text-primary hover:bg-primary/10 p-2 rounded-lg transition-colors">
                    <MaterialIcon name={session.icon} />
                  </button>
                </div>
              ))}
            </div>
          </div>

          {/* Recommended Topics */}
          <div className="bg-white dark:bg-card-dark p-6 rounded-xl border border-slate-200 dark:border-border-dark">
            <h4 className="font-bold mb-6">Recommended for You</h4>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {recommended.map((topic) => (
                <div
                  key={topic.title}
                  className="p-4 rounded-xl border border-slate-200 dark:border-border-dark hover:border-primary/50 transition-colors group cursor-pointer"
                >
                  <div
                    className={`size-10 rounded-lg ${topic.iconColor} flex items-center justify-center mb-4`}
                  >
                    <MaterialIcon name={topic.icon} />
                  </div>
                  <h5 className="font-bold text-sm group-hover:text-primary transition-colors">
                    {topic.title}
                  </h5>
                  <p className="text-xs text-slate-500 dark:text-slate-400 mt-1 line-clamp-2">
                    {topic.desc}
                  </p>
                  <div className="flex items-center gap-2 mt-4 text-[10px] font-bold text-slate-400 uppercase tracking-widest">
                    <MaterialIcon name="schedule" className="text-sm" />
                    {topic.duration}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
