export const onboardingSteps = [
  {
    id: "goal",
    title: "Learning Goal",
    description: "What do you want to master?",
    path: "/onboarding/goal",
  },
  {
    id: "preferences",
    title: "Preferences",
    description: "How do you learn best?",
    path: "/onboarding/preferences",
  },
  {
    id: "prerequisites",
    title: "Prerequisites",
    description: "What do you already know?",
    path: "/onboarding/prerequisites",
  },
  {
    id: "timeline",
    title: "Timeline",
    description: "When and how often?",
    path: "/onboarding/timeline",
  },
  {
    id: "assessment",
    title: "Skill Check",
    description: "Let's gauge your starting point",
    path: "/onboarding/assessment",
  },
  {
    id: "review",
    title: "Review",
    description: "Confirm your learning plan",
    path: "/onboarding/review",
  },
] as const;

export type OnboardingStepId = (typeof onboardingSteps)[number]["id"];
