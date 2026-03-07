import type {
  OnboardingStatus,
  EducationLevel,
  LearningStyle,
  ContentDepth,
  TeachingStyle,
  AssessmentType,
  GoalStatus,
  AgentType,
  AgentTaskStatus,
  SessionType,
  SessionStatus,
  CourseStatus,
  LessonType,
  ConfidenceLevel,
  ReadinessLevel,
  SessionFrequency,
} from "./index";

export interface Profile {
  id: string;
  name: string | null;
  email: string;
  avatar_url: string | null;
  education_level: EducationLevel | null;
  onboarding_status: OnboardingStatus;
  created_at: string;
  updated_at: string;
}

export interface UserPreferences {
  id: string;
  user_id: string;
  learning_style: LearningStyle;
  content_depth: ContentDepth;
  teaching_style: TeachingStyle;
  assessment_type: AssessmentType;
  session_frequency: SessionFrequency;
  session_duration_minutes: number;
  hours_per_week: number;
  learning_style_note: string;
  content_depth_note: string;
  teaching_style_note: string;
  assessment_type_note: string;
  education_level_note: string;
  accessibility: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface LearningGoal {
  id: string;
  user_id: string;
  title: string;
  end_goal: string | null;
  motivation: string | null;
  status: GoalStatus;
  is_exam_prep: boolean;
  exam_name: string | null;
  exam_date: string | null;
  created_at: string;
  updated_at: string;
}

export interface Prerequisite {
  id: string;
  goal_id: string;
  user_id: string;
  skill_name: string;
  confidence_level: ConfidenceLevel;
  notes: string | null;
  created_at: string;
}

export interface PrerequisiteAssessment {
  id: string;
  goal_id: string;
  user_id: string;
  questions: Record<string, unknown>[];
  score: number | null;
  readiness_level: ReadinessLevel;
  recommended_review_topics: string[];
  created_at: string;
}

export interface Course {
  id: string;
  goal_id: string;
  user_id: string;
  title: string;
  status: CourseStatus;
  curriculum: Record<string, unknown>;
  progress_percentage: number;
  created_at: string;
  updated_at: string;
}

export interface Lesson {
  id: string;
  course_id: string;
  user_id: string;
  title: string;
  lesson_type: LessonType;
  order_index: number;
  content: Record<string, unknown>;
  is_completed: boolean;
  created_at: string;
  updated_at: string;
}

export interface Session {
  id: string;
  user_id: string;
  course_id: string | null;
  lesson_id: string | null;
  title: string;
  session_type: SessionType;
  status: SessionStatus;
  scheduled_at: string | null;
  duration_minutes: number;
  notes: string | null;
  created_at: string;
  updated_at: string;
}

export interface AgentTask {
  id: string;
  goal_id: string;
  user_id: string;
  agent_type: AgentType;
  status: AgentTaskStatus;
  progress_percentage: number;
  current_task: string | null;
  focus: string | null;
  logs: AgentLog[];
  error_message: string | null;
  started_at: string | null;
  completed_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface AgentLog {
  timestamp: string;
  agent: string;
  message: string;
  level: "info" | "success" | "error" | "system";
}
