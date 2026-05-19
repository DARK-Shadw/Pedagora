"use client";

import { useEffect } from "react";
import { createClient } from "@/lib/supabase/client";
import { useAgentStore } from "@/stores/agent-store";
import type { AgentTask } from "@/types/database";

export function useAgentRealtime(goalId: string | null | undefined) {
  const { updateTask, addTask } = useAgentStore();

  useEffect(() => {
    if (!goalId) return;

    const supabase = createClient();

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

    return () => {
      supabase.removeChannel(taskChannel);
    };
  }, [goalId, updateTask, addTask]);
}
