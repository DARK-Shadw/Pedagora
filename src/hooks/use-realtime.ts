"use client";

import { useEffect } from "react";
import { createClient } from "@/lib/supabase/client";
import { useAgentStore } from "@/stores/agent-store";
import type { AgentTask } from "@/types/database";

export function useAgentRealtime(userId: string | undefined) {
  const { updateTask } = useAgentStore();

  useEffect(() => {
    if (!userId) return;

    const supabase = createClient();

    const channel = supabase
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

    return () => {
      supabase.removeChannel(channel);
    };
  }, [userId, updateTask]);
}
