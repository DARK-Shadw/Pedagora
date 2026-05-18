import type {
  LearningStyle,
  ContentDepth,
  TeachingStyle,
  AssessmentType,
  EducationLevel,
  ConfidenceLevel,
  SessionFrequency,
} from "./index";

export type ContentType = "course" | "single_episode";

export interface OnboardingGoalData {
  contentType: ContentType;
  title: string;
  endGoal: string;
  motivation: string;
  isExamPrep: boolean;
  examName: string;
  examDate: string;
}

export interface OnboardingPreferencesData {
  learningStyle: LearningStyle;
  contentDepth: ContentDepth;
  teachingStyle: TeachingStyle;
  assessmentType: AssessmentType;
  educationLevel: EducationLevel;
  learningStyleNote: string;
  contentDepthNote: string;
  teachingStyleNote: string;
  assessmentTypeNote: string;
  educationLevelNote: string;
}

export interface PrerequisiteItem {
  skillName: string;
  confidenceLevel: ConfidenceLevel;
  notes: string;
}

export interface OnboardingPrerequisitesData {
  prerequisites: PrerequisiteItem[];
}

export interface OnboardingTimelineData {
  targetDate: string;
  hoursPerWeek: number;
  sessionFrequency: SessionFrequency;
  sessionDurationMinutes: number;
}

export interface AssessmentQuestion {
  id: string;
  question: string;
  context: string;
}

export interface AssessmentAnswer {
  questionId: string;
  question: string;
  confidence: ConfidenceLevel;
}

export interface OnboardingAssessmentData {
  questions: AssessmentQuestion[];
  answers: AssessmentAnswer[];
}

export interface ResourceFileInfo {
  id: string;
  fileName: string;
  fileType: 'pdf' | 'pptx' | 'docx';
  fileSizeBytes: number;
}

export interface OnboardingResourcesData {
  files: ResourceFileInfo[];
}

export interface OnboardingData {
  goal: OnboardingGoalData;
  preferences: OnboardingPreferencesData;
  prerequisites: OnboardingPrerequisitesData;
  timeline: OnboardingTimelineData;
  assessment: OnboardingAssessmentData;
  resources: OnboardingResourcesData;
}
