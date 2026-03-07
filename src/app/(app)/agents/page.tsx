"use client";

import { useEffect, useState } from "react";
import { MaterialIcon } from "@/components/shared/material-icon";
import { createClient } from "@/lib/supabase/client";
import { useAgentStore } from "@/stores/agent-store";
import { useUser } from "@/hooks/use-user";
import { useAgentRealtime } from "@/hooks/use-realtime";
import type { AgentTask, AgentLog } from "@/types/database";

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

// Demo data for when no real tasks exist
const demoTasks: AgentTask[] = [
  {
    id: "demo-1",
    goal_id: "demo",
    user_id: "demo",
    agent_type: "research",
    status: "completed",
    progress_percentage: 100,
    current_task: "Verification complete",
    focus: "Academic Databases",
    logs: [
      { timestamp: "12:44:01", agent: "RESEARCH_AGENT", message: "Successfully indexed 245 candidate papers.", level: "info" },
      { timestamp: "12:44:12", agent: "RESEARCH_AGENT", message: "Cross-referencing findings with Oxford Learner's Corpus.", level: "info" },
      { timestamp: "12:44:28", agent: "SYSTEM", message: "Initial research synthesis phase marked COMPLETED.", level: "success" },
    ],
    error_message: null,
    started_at: null,
    completed_at: null,
    created_at: "",
    updated_at: "",
  },
  {
    id: "demo-2",
    goal_id: "demo",
    user_id: "demo",
    agent_type: "planning",
    status: "active",
    progress_percentage: 68,
    current_task: "Optimizing module Bloom's Taxonomy...",
    focus: "Learning Path",
    logs: [
      { timestamp: "12:44:30", agent: "PLANNING_AGENT", message: "Initializing learning objectives for Module 1-3.", level: "info" },
      { timestamp: "12:44:35", agent: "PLANNING_AGENT", message: "Mapping prerequisite nodes to knowledge graph.", level: "info" },
      { timestamp: "12:45:01", agent: "PLANNING_AGENT", message: "Optimizing path for cognitive load distribution...", level: "info" },
    ],
    error_message: null,
    started_at: null,
    completed_at: null,
    created_at: "",
    updated_at: "",
  },
  {
    id: "demo-3",
    goal_id: "demo",
    user_id: "demo",
    agent_type: "visualization",
    status: "queued",
    progress_percentage: 30,
    current_task: "Awaiting curriculum structure",
    focus: "Infographic Engine",
    logs: [],
    error_message: null,
    started_at: null,
    completed_at: null,
    created_at: "",
    updated_at: "",
  },
  {
    id: "demo-4",
    goal_id: "demo",
    user_id: "demo",
    agent_type: "teaching",
    status: "queued",
    progress_percentage: 0,
    current_task: "Waiting for prerequisites",
    focus: "Script Generation",
    logs: [],
    error_message: null,
    started_at: null,
    completed_at: null,
    created_at: "",
    updated_at: "",
  },
];

export default function AgentsPage() {
  const { user } = useUser();
  const { tasks, setTasks } = useAgentStore();
  const [loading, setLoading] = useState(true);

  useAgentRealtime(user?.id);

  useEffect(() => {
    async function fetchTasks() {
      if (!user) {
        setTasks(demoTasks);
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
      } else {
        setTasks(demoTasks);
      }
      setLoading(false);
    }

    fetchTasks();
  }, [user, setTasks]);

  // Collect all logs from all tasks
  const allLogs: AgentLog[] = tasks
    .flatMap((t) => (t.logs ?? []) as AgentLog[])
    .sort((a, b) => a.timestamp.localeCompare(b.timestamp));

  const activeTasks = tasks.filter(
    (t) => t.status === "active" || t.status === "queued"
  );
  const hasActive = activeTasks.length > 0;

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
            path.{" "}
            {hasActive && (
              <span className="text-primary font-medium">
                Estimated 2:45 remaining.
              </span>
            )}
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

          return (
            <div
              key={task.id}
              className={`group relative flex flex-col p-6 rounded-xl border border-primary/10 bg-white dark:bg-slate-900 shadow-sm transition-all hover:border-primary/30 ${
                isWaiting ? "opacity-70" : ""
              }`}
            >
              <div className="mb-4 flex items-center justify-between">
                <MaterialIcon
                  name={config.icon}
                  className="text-primary text-3xl"
                />
                <span className="text-[10px] font-bold uppercase tracking-widest text-slate-400">
                  Step {config.step}
                </span>
              </div>
              <h2 className="text-lg font-bold mb-1">{config.label}</h2>
              <p className="text-sm text-slate-500 mb-6">
                {task.current_task ?? "Waiting..."}
              </p>
              <div className="mt-auto">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-xs font-bold text-slate-400">
                    {statusLabels[task.status] ?? task.status.toUpperCase()}
                  </span>
                  <span
                    className={`text-xs font-mono font-bold ${
                      task.status === "completed" || task.status === "active"
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
                      task.status === "completed" || task.status === "active"
                        ? "bg-primary"
                        : "bg-slate-300 dark:bg-slate-600"
                    }`}
                    style={{ width: `${task.progress_percentage}%` }}
                  />
                </div>
              </div>
            </div>
          );
        })}
      </div>

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

                return (
                  <tr key={task.id}>
                    <td className="px-6 py-4 whitespace-nowrap text-sm font-medium">
                      {config.label.replace(" Agent", "")}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-slate-500">
                      {task.focus ?? "—"}
                    </td>
                    <td
                      className={`px-6 py-4 whitespace-nowrap text-sm ${
                        task.status === "completed"
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
                              isActive ? "bg-primary" : "bg-slate-300"
                            }`}
                            style={{
                              width: `${task.progress_percentage}%`,
                            }}
                          />
                        </div>
                        <span
                          className={`text-xs font-mono font-bold ${
                            isActive ? "text-primary" : "text-slate-400"
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
