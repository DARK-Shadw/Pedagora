"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { MaterialIcon } from "@/components/shared/material-icon";
import { createClient } from "@/lib/supabase/client";
import { useAgentStore } from "@/stores/agent-store";
import { useUser } from "@/hooks/use-user";
import { useAgentRealtime } from "@/hooks/use-realtime";
import type { AgentTask, AgentLog, ResearchResult } from "@/types/database";

const agentConfig: Record<
  string,
  { icon: string; step: number; label: string }
> = {
  research: { icon: "search_insights", step: 1, label: "Research Agent" },
  planning: { icon: "account_tree", step: 2, label: "Planning Agent" },
  visualization: { icon: "polyline", step: 3, label: "Visualization Agent" },
  teaching: { icon: "record_voice_over", step: 4, label: "Teaching Agent" },
};

const statusLabels: Record<string, string> = {
  queued: "QUEUED",
  active: "ACTIVE",
  completed: "COMPLETED",
  failed: "FAILED",
};

async function handleRetry(goalId: string) {
  const supabase = createClient();
  const { data: sessionData } = await supabase.auth.getSession();
  if (!sessionData.session?.access_token) return;

  const res = await fetch(`${process.env.NEXT_PUBLIC_BACKEND_URL}/agents/research`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${sessionData.session.access_token}`,
    },
    body: JSON.stringify({ goal_id: goalId }),
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    alert(err.detail || "Failed to retry research");
  }
}

function ResearchResultsPanel({ result }: { result: ResearchResult }) {
  const topicTree = result.topic_tree as { topic_groups?: { name: string }[]; effort_tier?: string };
  const synthesis = result.synthesis as {
    learning_path?: string[];
    key_themes?: string[];
  };
  const effortTier = topicTree.effort_tier;

  const topicCount = topicTree.topic_groups?.length ?? 0;
  const formulaCount = result.cross_topic_formulas?.length ?? 0;
  const exerciseCount = result.coding_exercises?.length ?? 0;
  const learningPath = synthesis.learning_path ?? [];
  const keyThemes = synthesis.key_themes ?? [];

  const stats = [
    { icon: "topic", label: "Topics", value: topicCount },
    { icon: "source", label: "Sources", value: result.source_count },
    { icon: "function", label: "Formulas", value: formulaCount },
    { icon: "code", label: "Exercises", value: exerciseCount },
  ];

  return (
    <div className="bg-white dark:bg-slate-900 rounded-xl border border-primary/10 shadow-sm overflow-hidden">
      <div className="px-6 py-4 border-b border-primary/5 flex items-center gap-3">
        <MaterialIcon name="labs" className="text-primary text-xl" />
        <h3 className="font-bold">Research Results</h3>
        {effortTier && (
          <span className={`ml-auto px-2 py-0.5 rounded text-[10px] font-bold uppercase tracking-wider ${
            effortTier === "light" ? "bg-emerald-500/10 text-emerald-400"
              : effortTier === "deep" ? "bg-amber-500/10 text-amber-400"
              : "bg-primary/10 text-primary"
          }`}>{effortTier} effort</span>
        )}
      </div>

      <div className="p-6 space-y-6">
        {/* Stats grid */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          {stats.map((stat) => (
            <div
              key={stat.label}
              className="flex flex-col items-center p-4 rounded-lg bg-slate-50 dark:bg-slate-800/50"
            >
              <MaterialIcon name={stat.icon} className="text-primary text-2xl mb-1" />
              <span className="text-2xl font-black text-primary">{stat.value}</span>
              <span className="text-xs font-bold uppercase tracking-wider text-slate-400">
                {stat.label}
              </span>
            </div>
          ))}
        </div>

        {/* Learning path */}
        {learningPath.length > 0 && (
          <div>
            <h4 className="text-xs font-bold uppercase tracking-widest text-slate-400 mb-3">
              Learning Path
            </h4>
            <ol className="space-y-2">
              {learningPath.map((topic, i) => (
                <li key={i} className="flex items-center gap-3 text-sm">
                  <span className="flex items-center justify-center w-6 h-6 rounded-full bg-primary/10 text-primary text-xs font-bold shrink-0">
                    {i + 1}
                  </span>
                  <span className="text-slate-700 dark:text-slate-300">{topic}</span>
                </li>
              ))}
            </ol>
          </div>
        )}

        {/* Key themes */}
        {keyThemes.length > 0 && (
          <div>
            <h4 className="text-xs font-bold uppercase tracking-widest text-slate-400 mb-3">
              Key Themes
            </h4>
            <div className="flex flex-wrap gap-2">
              {keyThemes.map((theme, i) => (
                <span
                  key={i}
                  className="px-3 py-1 rounded-full text-xs font-medium bg-primary/10 text-primary"
                >
                  {theme}
                </span>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

export default function AgentsPage() {
  const { user } = useUser();
  const { tasks, setTasks, researchResult, setResearchResult } = useAgentStore();
  const [loading, setLoading] = useState(true);
  const [retrying, setRetrying] = useState(false);

  useAgentRealtime(user?.id);

  useEffect(() => {
    async function fetchTasks() {
      if (!user) {
        setTasks([]);
        setLoading(false);
        return;
      }

      const supabase = createClient();
      const { data } = await supabase
        .from("agent_tasks")
        .select("*")
        .eq("user_id", user.id)
        .order("created_at", { ascending: true });

      if (data && data.length > 0) {
        setTasks(data as AgentTask[]);

        // Check for completed research and fetch results
        const researchTask = data.find(
          (t: AgentTask) => t.agent_type === "research" && t.status === "completed"
        );
        if (researchTask) {
          const { data: result } = await supabase
            .from("research_results")
            .select("*")
            .eq("goal_id", researchTask.goal_id)
            .single();
          if (result) setResearchResult(result as ResearchResult);
        }
      } else {
        setTasks([]);
      }
      setLoading(false);
    }

    fetchTasks();
  }, [user, setTasks, setResearchResult]);

  // Collect all logs from all tasks
  const allLogs: AgentLog[] = tasks
    .flatMap((t) => (t.logs ?? []) as AgentLog[])
    .sort((a, b) => a.timestamp.localeCompare(b.timestamp));

  const activeTasks = tasks.filter(
    (t) => t.status === "active" || t.status === "queued"
  );
  const hasActive = activeTasks.length > 0;

  const researchTask = tasks.find((t) => t.agent_type === "research");
  const researchFailed = researchTask?.status === "failed";

  async function onRetry() {
    if (!researchTask || retrying) return;
    setRetrying(true);
    await handleRetry(researchTask.goal_id);
    setRetrying(false);
  }

  if (loading) {
    return (
      <div className="p-8 space-y-8 max-w-7xl mx-auto w-full animate-pulse">
        <div className="h-8 w-64 bg-muted rounded" />
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
          {[1, 2, 3, 4].map((i) => (
            <div key={i} className="h-48 bg-muted rounded-xl" />
          ))}
        </div>
      </div>
    );
  }

  if (tasks.length === 0) {
    return (
      <div className="p-4 md:p-8 max-w-7xl mx-auto w-full">
        <h1 className="text-3xl md:text-4xl font-black tracking-tight mb-2">
          Curriculum Synthesis
        </h1>
        <p className="text-slate-500 dark:text-slate-400 mb-12">
          Your AI agents will appear here once you create a learning goal.
        </p>
        <div className="flex flex-col items-center justify-center py-20 text-center">
          <div className="size-16 rounded-2xl bg-primary/10 text-primary flex items-center justify-center mb-6">
            <MaterialIcon name="rocket_launch" className="text-3xl" />
          </div>
          <h3 className="text-xl font-bold mb-2">No active goals</h3>
          <p className="text-sm text-slate-500 max-w-sm mb-6">
            Create your first learning goal to launch the AI pipeline.
          </p>
          <Link
            href="/onboarding/goal"
            className="inline-flex items-center gap-2 px-5 py-2.5 rounded-lg bg-primary text-white text-sm font-bold hover:bg-primary/90 transition-colors"
          >
            Create a Goal
            <MaterialIcon name="arrow_forward" className="text-base" />
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="p-4 md:p-8 space-y-8 max-w-7xl mx-auto w-full">
      {/* Title & Status */}
      <div className="flex flex-col md:flex-row md:items-end justify-between gap-4">
        <div>
          <h1 className="text-3xl md:text-4xl font-black tracking-tight mb-2">
            Curriculum Synthesis
          </h1>
          <p className="text-slate-500 dark:text-slate-400 max-w-2xl">
            Pedagora AI agents are collaborating to build your custom learning
            path.
          </p>
        </div>
        {hasActive && (
          <div className="flex items-center gap-2 text-sm font-medium text-slate-400 bg-white dark:bg-slate-800 px-4 py-2 rounded-lg border border-primary/10">
            <span className="relative flex h-2 w-2">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-primary opacity-75" />
              <span className="relative inline-flex rounded-full h-2 w-2 bg-primary" />
            </span>
            System Live
          </div>
        )}
      </div>

      {/* Agent Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
        {tasks.map((task) => {
          const config = agentConfig[task.agent_type];
          if (!config) return null;
          const isWaiting = task.status === "queued" && task.progress_percentage === 0;
          const isFailed = task.status === "failed";
          const isResearch = task.agent_type === "research";

          return (
            <div
              key={task.id}
              className={`group relative flex flex-col p-6 rounded-xl border bg-white dark:bg-slate-900 shadow-sm transition-all hover:border-primary/30 ${
                isFailed
                  ? "border-red-500/30"
                  : "border-primary/10"
              } ${isWaiting ? "opacity-70" : ""}`}
            >
              <div className="mb-4 flex items-center justify-between">
                <MaterialIcon
                  name={config.icon}
                  className={`text-3xl ${isFailed ? "text-red-400" : "text-primary"}`}
                />
                <span className="text-[10px] font-bold uppercase tracking-widest text-slate-400">
                  Step {config.step}
                </span>
              </div>
              <h2 className="text-lg font-bold mb-1">
                {config.label}
                {task.agent_type === "research" && task.metadata?.effort_tier && (
                  <span className={`ml-2 px-2 py-0.5 rounded text-[10px] font-bold uppercase tracking-wider ${
                    task.metadata.effort_tier === "light" ? "bg-emerald-500/10 text-emerald-400"
                      : task.metadata.effort_tier === "deep" ? "bg-amber-500/10 text-amber-400"
                      : "bg-primary/10 text-primary"
                  }`}>{task.metadata.effort_tier}</span>
                )}
              </h2>
              <p className={`text-sm mb-6 ${isFailed ? "text-red-400" : "text-slate-500"}`}>
                {isFailed
                  ? task.error_message || "Research failed"
                  : task.current_task ?? "Waiting..."}
              </p>
              <div className="mt-auto">
                <div className="flex items-center justify-between mb-2">
                  <span className={`text-xs font-bold ${isFailed ? "text-red-400" : "text-slate-400"}`}>
                    {statusLabels[task.status] ?? task.status.toUpperCase()}
                  </span>
                  <span
                    className={`text-xs font-mono font-bold ${
                      isFailed
                        ? "text-red-400"
                        : task.status === "completed" || task.status === "active"
                          ? "text-primary"
                          : "text-slate-400"
                    }`}
                  >
                    {task.progress_percentage}%
                  </span>
                </div>
                <div className="h-1.5 w-full bg-slate-100 dark:bg-slate-800 rounded-full overflow-hidden">
                  <div
                    className={`h-full rounded-full transition-all ${
                      isFailed
                        ? "bg-red-500"
                        : task.status === "completed" || task.status === "active"
                          ? "bg-primary"
                          : "bg-slate-300 dark:bg-slate-600"
                    }`}
                    style={{ width: `${task.progress_percentage}%` }}
                  />
                </div>
                {/* Retry button for failed research */}
                {isFailed && isResearch && (
                  <button
                    onClick={onRetry}
                    disabled={retrying}
                    className="mt-4 w-full flex items-center justify-center gap-2 px-4 py-2 rounded-lg bg-red-500/10 text-red-400 hover:bg-red-500/20 text-sm font-medium transition-colors disabled:opacity-50"
                  >
                    <MaterialIcon
                      name="refresh"
                      className={`text-base ${retrying ? "animate-spin" : ""}`}
                    />
                    {retrying ? "Retrying..." : "Retry Research"}
                  </button>
                )}
              </div>
            </div>
          );
        })}
      </div>

      {/* Research Results Panel */}
      {researchResult && <ResearchResultsPanel result={researchResult} />}

      {/* Pipeline Table */}
      <div className="bg-white dark:bg-slate-900 rounded-xl border border-primary/10 overflow-hidden shadow-sm">
        <div className="px-6 py-4 border-b border-primary/5 flex items-center justify-between">
          <h3 className="font-bold">Live Execution Pipeline</h3>
          <div className="flex gap-2">
            <div className="h-2 w-2 rounded-full bg-primary/20" />
            <div className="h-2 w-2 rounded-full bg-primary" />
            <div className="h-2 w-2 rounded-full bg-primary/20" />
          </div>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-left">
            <thead className="bg-slate-50 dark:bg-slate-800/50">
              <tr>
                <th className="px-6 py-3 text-xs font-bold uppercase tracking-wider text-slate-400">
                  Agent
                </th>
                <th className="px-6 py-3 text-xs font-bold uppercase tracking-wider text-slate-400">
                  Focus
                </th>
                <th className="px-6 py-3 text-xs font-bold uppercase tracking-wider text-slate-400">
                  Current Task
                </th>
                <th className="px-6 py-3 text-xs font-bold uppercase tracking-wider text-slate-400 text-right">
                  Progress
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-primary/5">
              {tasks.map((task) => {
                const config = agentConfig[task.agent_type];
                if (!config) return null;
                const isActive =
                  task.status === "active" || task.status === "completed";
                const isFailed = task.status === "failed";

                return (
                  <tr key={task.id}>
                    <td className="px-6 py-4 whitespace-nowrap text-sm font-medium">
                      {config.label.replace(" Agent", "")}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-slate-500">
                      {task.focus ?? "\u2014"}
                    </td>
                    <td
                      className={`px-6 py-4 whitespace-nowrap text-sm ${
                        isFailed
                          ? "text-red-400 font-medium"
                          : task.status === "completed"
                            ? "text-primary font-medium"
                            : "text-slate-600 dark:text-slate-400"
                      }`}
                    >
                      {task.current_task ?? "Waiting..."}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-right">
                      <div className="flex items-center justify-end gap-3">
                        <div className="w-24 bg-slate-100 dark:bg-slate-800 h-1 rounded-full">
                          <div
                            className={`h-full rounded-full ${
                              isFailed
                                ? "bg-red-500"
                                : isActive
                                  ? "bg-primary"
                                  : "bg-slate-300"
                            }`}
                            style={{
                              width: `${task.progress_percentage}%`,
                            }}
                          />
                        </div>
                        <span
                          className={`text-xs font-mono font-bold ${
                            isFailed
                              ? "text-red-400"
                              : isActive
                                ? "text-primary"
                                : "text-slate-400"
                          }`}
                        >
                          {task.progress_percentage}%
                        </span>
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>

      {/* Execution Logs */}
      <div className="space-y-4">
        <h3 className="text-xs font-bold uppercase tracking-widest text-slate-400 px-1">
          System Execution Logs
        </h3>
        <div className="bg-slate-900 dark:bg-black p-6 rounded-lg border border-primary/20 font-mono text-[11px] leading-relaxed text-primary/80 overflow-y-auto max-h-48">
          {allLogs.length > 0 ? (
            allLogs.map((log, i) => (
              <div key={i} className="flex gap-4">
                <span className="text-slate-600 shrink-0">
                  [{log.timestamp}]
                </span>
                <span
                  className={
                    log.level === "success"
                      ? "text-white"
                      : log.level === "error"
                        ? "text-red-400"
                        : ""
                  }
                >
                  {log.agent}: {log.message}
                </span>
              </div>
            ))
          ) : (
            <div className="text-slate-600">
              No execution logs yet. Agents will report activity here.
            </div>
          )}
          <div className="flex gap-4 mt-2">
            <span className="text-primary animate-pulse">_</span>
          </div>
        </div>
      </div>
    </div>
  );
}
