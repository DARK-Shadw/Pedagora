import { create } from "zustand";
import type { AgentTask, ResearchResult } from "@/types/database";

interface AgentState {
  tasks: AgentTask[];
  activeGoalId: string | null;
  researchResult: ResearchResult | null;
  setTasks: (tasks: AgentTask[]) => void;
  setActiveGoalId: (id: string | null) => void;
  updateTask: (task: AgentTask) => void;
  addTask: (task: AgentTask) => void;
  setResearchResult: (result: ResearchResult | null) => void;
}

export const useAgentStore = create<AgentState>((set) => ({
  tasks: [],
  activeGoalId: null,
  researchResult: null,
  setTasks: (tasks) => set({ tasks }),
  setActiveGoalId: (activeGoalId) => set({ activeGoalId }),
  updateTask: (task) =>
    set((state) => ({
      tasks: state.tasks.map((t) => (t.id === task.id ? task : t)),
    })),
  addTask: (task) =>
    set((state) => {
      // Don't add duplicates (realtime can fire multiple times)
      if (state.tasks.some((t) => t.id === task.id)) return state;
      return { tasks: [...state.tasks, task].sort(
        (a, b) => a.created_at.localeCompare(b.created_at)
      )};
    }),
  setResearchResult: (researchResult) => set({ researchResult }),
}));
