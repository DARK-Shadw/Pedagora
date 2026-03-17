"use client";

import { useEffect } from "react";
import { createClient } from "@/lib/supabase/client";
import { useAgentStore } from "@/stores/agent-store";
import type { AgentTask, ResearchResult } from "@/types/database";

export function useAgentRealtime(userId: string | undefined) {
  const { updateTask, setResearchResult } = useAgentStore();

  useEffect(() => {
    if (!userId) return;

    const supabase = createClient();

    const taskChannel = supabase
      .channel("agent-tasks")
      .on(
        "postgres_changes",
        {
          event: "UPDATE",
          schema: "public",
          table: "agent_tasks",
          filter: `user_id=eq.${userId}`,
        },
        (payload) => {
          updateTask(payload.new as AgentTask);
        }
      )
      .subscribe();

    const resultChannel = supabase
      .channel("research-results")
      .on(
        "postgres_changes",
        {
          event: "*",
          schema: "public",
          table: "research_results",
          filter: `user_id=eq.${userId}`,
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
  }, [userId, updateTask, setResearchResult]);
}
