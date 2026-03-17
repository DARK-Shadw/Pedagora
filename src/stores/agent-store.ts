import { create } from "zustand";
import type { AgentTask, ResearchResult } from "@/types/database";

interface AgentState {
  tasks: AgentTask[];
  researchResult: ResearchResult | null;
  setTasks: (tasks: AgentTask[]) => void;
  updateTask: (task: AgentTask) => void;
  setResearchResult: (result: ResearchResult | null) => void;
}

export const useAgentStore = create<AgentState>((set) => ({
  tasks: [],
  researchResult: null,
  setTasks: (tasks) => set({ tasks }),
  updateTask: (task) =>
    set((state) => ({
      tasks: state.tasks.map((t) => (t.id === task.id ? task : t)),
    })),
  setResearchResult: (researchResult) => set({ researchResult }),
}));
