import { create } from "zustand";
import type { AgentTask } from "@/types/database";

interface AgentState {
  tasks: AgentTask[];
  setTasks: (tasks: AgentTask[]) => void;
  updateTask: (task: AgentTask) => void;
}

export const useAgentStore = create<AgentState>((set) => ({
  tasks: [],
  setTasks: (tasks) => set({ tasks }),
  updateTask: (task) =>
    set((state) => ({
      tasks: state.tasks.map((t) => (t.id === task.id ? task : t)),
    })),
}));
