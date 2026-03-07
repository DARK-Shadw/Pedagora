import { create } from "zustand";
import { persist } from "zustand/middleware";
import type {
  OnboardingGoalData,
  OnboardingPreferencesData,
  OnboardingPrerequisitesData,
  OnboardingTimelineData,
  OnboardingAssessmentData,
} from "@/types/onboarding";

interface OnboardingState {
  currentStep: number;
  goal: OnboardingGoalData;
  preferences: OnboardingPreferencesData;
  prerequisites: OnboardingPrerequisitesData;
  timeline: OnboardingTimelineData;
  assessment: OnboardingAssessmentData;
  setGoal: (data: OnboardingGoalData) => void;
  setPreferences: (data: OnboardingPreferencesData) => void;
  setPrerequisites: (data: OnboardingPrerequisitesData) => void;
  setTimeline: (data: OnboardingTimelineData) => void;
  setAssessment: (data: OnboardingAssessmentData) => void;
  setCurrentStep: (step: number) => void;
  reset: () => void;
}

const initialGoal: OnboardingGoalData = {
  title: "",
  endGoal: "",
  motivation: "",
  isExamPrep: false,
  examName: "",
  examDate: "",
};

const initialPreferences: OnboardingPreferencesData = {
  learningStyle: "visual",
  contentDepth: "intermediate",
  teachingStyle: "socratic",
  assessmentType: "mixed",
  educationLevel: "self_learner",
  learningStyleNote: "",
  contentDepthNote: "",
  teachingStyleNote: "",
  assessmentTypeNote: "",
  educationLevelNote: "",
};

const initialPrerequisites: OnboardingPrerequisitesData = {
  prerequisites: [],
};

const initialTimeline: OnboardingTimelineData = {
  targetDate: "",
  hoursPerWeek: 5,
  sessionFrequency: "three_per_week",
  sessionDurationMinutes: 45,
};

const initialAssessment: OnboardingAssessmentData = {
  questions: [],
  answers: [],
};

export const useOnboardingStore = create<OnboardingState>()(
  persist(
    (set) => ({
      currentStep: 0,
      goal: initialGoal,
      preferences: initialPreferences,
      prerequisites: initialPrerequisites,
      timeline: initialTimeline,
      assessment: initialAssessment,
      setGoal: (data) => set({ goal: data }),
      setPreferences: (data) => set({ preferences: data }),
      setPrerequisites: (data) => set({ prerequisites: data }),
      setTimeline: (data) => set({ timeline: data }),
      setAssessment: (data) => set({ assessment: data }),
      setCurrentStep: (step) => set({ currentStep: step }),
      reset: () =>
        set({
          currentStep: 0,
          goal: initialGoal,
          preferences: initialPreferences,
          prerequisites: initialPrerequisites,
          timeline: initialTimeline,
          assessment: initialAssessment,
        }),
    }),
    {
      name: "pedagora-onboarding",
    }
  )
);
