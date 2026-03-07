export const ROUTES = {
  home: "/",
  login: "/login",
  signup: "/signup",
  callback: "/callback",
  onboarding: "/onboarding",
  onboardingGoal: "/onboarding/goal",
  onboardingPreferences: "/onboarding/preferences",
  onboardingPrerequisites: "/onboarding/prerequisites",
  onboardingTimeline: "/onboarding/timeline",
  onboardingReview: "/onboarding/review",
  dashboard: "/dashboard",
  courses: "/courses",
  sessions: "/sessions",
  agents: "/agents",
  insights: "/insights",
  settings: "/settings",
} as const;

export const PROTECTED_ROUTES = [
  "/dashboard",
  "/courses",
  "/sessions",
  "/agents",
  "/insights",
  "/settings",
  "/onboarding",
];

export const AUTH_ROUTES = ["/login", "/signup"];
