import { z } from "zod";

export const goalSchema = z.object({
  title: z.string().min(3, "Please describe what you want to learn"),
  endGoal: z.string(),
  motivation: z.string(),
  isExamPrep: z.boolean(),
  examName: z.string(),
  examDate: z.string(),
});

export const preferencesSchema = z.object({
  learningStyle: z.enum(["visual", "depth_first", "fast_paced", "balanced"]),
  contentDepth: z.enum(["overview", "intermediate", "deep_dive"]),
  teachingStyle: z.enum(["socratic", "lecture", "example_based", "project_based"]),
  assessmentType: z.enum(["quiz", "project", "mixed", "none"]),
  educationLevel: z.enum([
    "high_school",
    "undergraduate",
    "graduate",
    "postgraduate",
    "professional",
    "self_learner",
  ]),
  learningStyleNote: z.string(),
  contentDepthNote: z.string(),
  teachingStyleNote: z.string(),
  assessmentTypeNote: z.string(),
  educationLevelNote: z.string(),
});

export const prerequisiteItemSchema = z.object({
  skillName: z.string().min(1, "Skill name is required"),
  confidenceLevel: z.enum(["none", "beginner", "intermediate", "advanced"]),
  notes: z.string(),
});

export const prerequisitesSchema = z.object({
  prerequisites: z.array(prerequisiteItemSchema),
});

export const timelineSchema = z.object({
  targetDate: z.string(),
  hoursPerWeek: z.number().min(1).max(40),
  sessionFrequency: z.enum(["daily", "every_other_day", "three_per_week", "weekly"]),
  sessionDurationMinutes: z.number().min(15).max(180),
});

export const assessmentAnswerSchema = z.object({
  questionId: z.string().min(1),
  question: z.string().min(1),
  confidence: z.enum(["none", "beginner", "intermediate", "advanced"]),
});

export const assessmentSchema = z.object({
  answers: z.array(assessmentAnswerSchema).min(1),
});

export type GoalInput = z.infer<typeof goalSchema>;
export type PreferencesInput = z.infer<typeof preferencesSchema>;
export type PrerequisiteItemInput = z.infer<typeof prerequisiteItemSchema>;
export type PrerequisitesInput = z.infer<typeof prerequisitesSchema>;
export type TimelineInput = z.infer<typeof timelineSchema>;
