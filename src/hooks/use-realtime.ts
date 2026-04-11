"use client";

import { useEffect } from "react";
import { createClient } from "@/lib/supabase/client";
import { useAgentStore } from "@/stores/agent-store";
import type { AgentTask, ResearchResult } from "@/types/database";

export function useAgentRealtime(goalId: string | null | undefined) {
  const { updateTask, addTask, setResearchResult } = useAgentStore();

  useEffect(() => {
    if (!goalId) return;

    const supabase = createClient();

    // Subscribe to INSERT + UPDATE for this specific goal's tasks.
    // Using goal_id filter (single predicate — Supabase Realtime limitation).
    // RLS enforces user scoping so no extra user_id filter is needed.
    const taskChannel = supabase
      .channel(`agent-tasks-${goalId}`)
      .on(
        "postgres_changes",
        {
          event: "*",
          schema: "public",
          table: "agent_tasks",
          filter: `goal_id=eq.${goalId}`,
        },
        (payload) => {
          if (payload.eventType === "INSERT") {
            addTask(payload.new as AgentTask);
          } else if (payload.eventType === "UPDATE") {
            updateTask(payload.new as AgentTask);
          }
        }
      )
      .subscribe();

    // Research results — scoped to this goal
    const resultChannel = supabase
      .channel(`research-results-${goalId}`)
      .on(
        "postgres_changes",
        {
          event: "*",
          schema: "public",
          table: "research_results",
          filter: `goal_id=eq.${goalId}`,
        },
        (payload) => {
          setResearchResult(payload.new as ResearchResult);
        }
      )
      .subscribe();

    return () => {
      supabase.removeChannel(taskChannel);
      supabase.removeChannel(resultChannel);
    };
  }, [goalId, updateTask, addTask, setResearchResult]);
}
