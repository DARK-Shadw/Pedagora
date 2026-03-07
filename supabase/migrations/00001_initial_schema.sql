-- Pedagora Initial Schema
-- Run this migration in Supabase SQL Editor

-- ============================================================
-- ENUMS
-- ============================================================

CREATE TYPE onboarding_status AS ENUM ('not_started', 'in_progress', 'completed');
CREATE TYPE education_level AS ENUM ('high_school', 'undergraduate', 'graduate', 'postgraduate', 'professional', 'self_learner');
CREATE TYPE learning_style AS ENUM ('visual', 'depth_first', 'fast_paced', 'balanced');
CREATE TYPE content_depth AS ENUM ('overview', 'intermediate', 'deep_dive');
CREATE TYPE teaching_style AS ENUM ('socratic', 'lecture', 'example_based', 'project_based');
CREATE TYPE assessment_type AS ENUM ('quiz', 'project', 'mixed', 'none');
CREATE TYPE goal_status AS ENUM ('active', 'completed', 'paused', 'abandoned');
CREATE TYPE agent_type AS ENUM ('research', 'planning', 'visualization', 'teaching');
CREATE TYPE agent_task_status AS ENUM ('queued', 'active', 'completed', 'failed');
CREATE TYPE session_type AS ENUM ('lesson', 'review', 'assessment', 'live');
CREATE TYPE session_status AS ENUM ('scheduled', 'in_progress', 'completed', 'cancelled');
CREATE TYPE course_status AS ENUM ('generating', 'active', 'completed', 'archived');
CREATE TYPE lesson_type AS ENUM ('theory', 'practice', 'visualization', 'assessment');
CREATE TYPE confidence_level AS ENUM ('none', 'beginner', 'intermediate', 'advanced');
CREATE TYPE readiness_level AS ENUM ('not_ready', 'needs_review', 'ready');
CREATE TYPE session_frequency AS ENUM ('daily', 'every_other_day', 'three_per_week', 'weekly');

-- ============================================================
-- HELPER: auto-update updated_at
-- ============================================================

CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = NOW();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- ============================================================
-- PROFILES (extends auth.users 1:1)
-- ============================================================

CREATE TABLE profiles (
  id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
  name TEXT,
  email TEXT NOT NULL,
  avatar_url TEXT,
  education_level education_level,
  onboarding_status onboarding_status NOT NULL DEFAULT 'not_started',
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TRIGGER profiles_updated_at
  BEFORE UPDATE ON profiles
  FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Auto-create profile on signup
CREATE OR REPLACE FUNCTION handle_new_user()
RETURNS TRIGGER AS $$
BEGIN
  INSERT INTO public.profiles (id, email, name, avatar_url)
  VALUES (
    NEW.id,
    NEW.email,
    COALESCE(NEW.raw_user_meta_data->>'name', NEW.raw_user_meta_data->>'full_name'),
    NEW.raw_user_meta_data->>'avatar_url'
  );
  RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

CREATE TRIGGER on_auth_user_created
  AFTER INSERT ON auth.users
  FOR EACH ROW EXECUTE FUNCTION handle_new_user();

-- ============================================================
-- USER PREFERENCES (1:1 per user)
-- ============================================================

CREATE TABLE user_preferences (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL UNIQUE REFERENCES profiles(id) ON DELETE CASCADE,
  learning_style learning_style NOT NULL DEFAULT 'balanced',
  content_depth content_depth NOT NULL DEFAULT 'intermediate',
  teaching_style teaching_style NOT NULL DEFAULT 'socratic',
  assessment_type assessment_type NOT NULL DEFAULT 'mixed',
  session_frequency session_frequency NOT NULL DEFAULT 'three_per_week',
  session_duration_minutes INTEGER NOT NULL DEFAULT 45,
  hours_per_week INTEGER NOT NULL DEFAULT 5,
  accessibility JSONB NOT NULL DEFAULT '{}',
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TRIGGER user_preferences_updated_at
  BEFORE UPDATE ON user_preferences
  FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- ============================================================
-- LEARNING GOALS (1:many per user)
-- ============================================================

CREATE TABLE learning_goals (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
  title TEXT NOT NULL,
  end_goal TEXT,
  motivation TEXT,
  status goal_status NOT NULL DEFAULT 'active',
  is_exam_prep BOOLEAN NOT NULL DEFAULT FALSE,
  exam_name TEXT,
  exam_date DATE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TRIGGER learning_goals_updated_at
  BEFORE UPDATE ON learning_goals
  FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- ============================================================
-- PREREQUISITES (1:many per goal)
-- ============================================================

CREATE TABLE prerequisites (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  goal_id UUID NOT NULL REFERENCES learning_goals(id) ON DELETE CASCADE,
  user_id UUID NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
  skill_name TEXT NOT NULL,
  confidence_level confidence_level NOT NULL DEFAULT 'none',
  notes TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ============================================================
-- PREREQUISITE ASSESSMENTS (1:many per goal)
-- ============================================================

CREATE TABLE prerequisite_assessments (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  goal_id UUID NOT NULL REFERENCES learning_goals(id) ON DELETE CASCADE,
  user_id UUID NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
  questions JSONB NOT NULL DEFAULT '[]',
  score NUMERIC(5,2),
  readiness_level readiness_level NOT NULL DEFAULT 'not_ready',
  recommended_review_topics TEXT[] NOT NULL DEFAULT '{}',
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ============================================================
-- COURSES (1:many per goal, typically 1)
-- ============================================================

CREATE TABLE courses (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  goal_id UUID NOT NULL REFERENCES learning_goals(id) ON DELETE CASCADE,
  user_id UUID NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
  title TEXT NOT NULL,
  status course_status NOT NULL DEFAULT 'generating',
  curriculum JSONB NOT NULL DEFAULT '{}',
  progress_percentage NUMERIC(5,2) NOT NULL DEFAULT 0,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TRIGGER courses_updated_at
  BEFORE UPDATE ON courses
  FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- ============================================================
-- LESSONS (1:many per course)
-- ============================================================

CREATE TABLE lessons (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  course_id UUID NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
  user_id UUID NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
  title TEXT NOT NULL,
  lesson_type lesson_type NOT NULL DEFAULT 'theory',
  order_index INTEGER NOT NULL DEFAULT 0,
  content JSONB NOT NULL DEFAULT '{}',
  is_completed BOOLEAN NOT NULL DEFAULT FALSE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TRIGGER lessons_updated_at
  BEFORE UPDATE ON lessons
  FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- ============================================================
-- SESSIONS (1:many per user)
-- ============================================================

CREATE TABLE sessions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
  course_id UUID REFERENCES courses(id) ON DELETE SET NULL,
  lesson_id UUID REFERENCES lessons(id) ON DELETE SET NULL,
  title TEXT NOT NULL,
  session_type session_type NOT NULL DEFAULT 'lesson',
  status session_status NOT NULL DEFAULT 'scheduled',
  scheduled_at TIMESTAMPTZ,
  duration_minutes INTEGER NOT NULL DEFAULT 45,
  notes TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TRIGGER sessions_updated_at
  BEFORE UPDATE ON sessions
  FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- ============================================================
-- AGENT TASKS (1:many per goal)
-- ============================================================

CREATE TABLE agent_tasks (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  goal_id UUID NOT NULL REFERENCES learning_goals(id) ON DELETE CASCADE,
  user_id UUID NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
  agent_type agent_type NOT NULL,
  status agent_task_status NOT NULL DEFAULT 'queued',
  progress_percentage NUMERIC(5,2) NOT NULL DEFAULT 0,
  current_task TEXT,
  focus TEXT,
  logs JSONB NOT NULL DEFAULT '[]',
  error_message TEXT,
  started_at TIMESTAMPTZ,
  completed_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TRIGGER agent_tasks_updated_at
  BEFORE UPDATE ON agent_tasks
  FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- ============================================================
-- ROW LEVEL SECURITY
-- ============================================================

ALTER TABLE profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE user_preferences ENABLE ROW LEVEL SECURITY;
ALTER TABLE learning_goals ENABLE ROW LEVEL SECURITY;
ALTER TABLE prerequisites ENABLE ROW LEVEL SECURITY;
ALTER TABLE prerequisite_assessments ENABLE ROW LEVEL SECURITY;
ALTER TABLE courses ENABLE ROW LEVEL SECURITY;
ALTER TABLE lessons ENABLE ROW LEVEL SECURITY;
ALTER TABLE sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE agent_tasks ENABLE ROW LEVEL SECURITY;

-- Profiles: users can read/update their own profile
CREATE POLICY "Users can view own profile"
  ON profiles FOR SELECT USING (auth.uid() = id);
CREATE POLICY "Users can update own profile"
  ON profiles FOR UPDATE USING (auth.uid() = id);

-- User Preferences
CREATE POLICY "Users can view own preferences"
  ON user_preferences FOR SELECT USING (auth.uid() = user_id);
CREATE POLICY "Users can insert own preferences"
  ON user_preferences FOR INSERT WITH CHECK (auth.uid() = user_id);
CREATE POLICY "Users can update own preferences"
  ON user_preferences FOR UPDATE USING (auth.uid() = user_id);

-- Learning Goals
CREATE POLICY "Users can view own goals"
  ON learning_goals FOR SELECT USING (auth.uid() = user_id);
CREATE POLICY "Users can insert own goals"
  ON learning_goals FOR INSERT WITH CHECK (auth.uid() = user_id);
CREATE POLICY "Users can update own goals"
  ON learning_goals FOR UPDATE USING (auth.uid() = user_id);
CREATE POLICY "Users can delete own goals"
  ON learning_goals FOR DELETE USING (auth.uid() = user_id);

-- Prerequisites
CREATE POLICY "Users can view own prerequisites"
  ON prerequisites FOR SELECT USING (auth.uid() = user_id);
CREATE POLICY "Users can insert own prerequisites"
  ON prerequisites FOR INSERT WITH CHECK (auth.uid() = user_id);
CREATE POLICY "Users can update own prerequisites"
  ON prerequisites FOR UPDATE USING (auth.uid() = user_id);
CREATE POLICY "Users can delete own prerequisites"
  ON prerequisites FOR DELETE USING (auth.uid() = user_id);

-- Prerequisite Assessments
CREATE POLICY "Users can view own assessments"
  ON prerequisite_assessments FOR SELECT USING (auth.uid() = user_id);
CREATE POLICY "Users can insert own assessments"
  ON prerequisite_assessments FOR INSERT WITH CHECK (auth.uid() = user_id);

-- Courses
CREATE POLICY "Users can view own courses"
  ON courses FOR SELECT USING (auth.uid() = user_id);
CREATE POLICY "Users can insert own courses"
  ON courses FOR INSERT WITH CHECK (auth.uid() = user_id);
CREATE POLICY "Users can update own courses"
  ON courses FOR UPDATE USING (auth.uid() = user_id);

-- Lessons
CREATE POLICY "Users can view own lessons"
  ON lessons FOR SELECT USING (auth.uid() = user_id);
CREATE POLICY "Users can insert own lessons"
  ON lessons FOR INSERT WITH CHECK (auth.uid() = user_id);
CREATE POLICY "Users can update own lessons"
  ON lessons FOR UPDATE USING (auth.uid() = user_id);

-- Sessions
CREATE POLICY "Users can view own sessions"
  ON sessions FOR SELECT USING (auth.uid() = user_id);
CREATE POLICY "Users can insert own sessions"
  ON sessions FOR INSERT WITH CHECK (auth.uid() = user_id);
CREATE POLICY "Users can update own sessions"
  ON sessions FOR UPDATE USING (auth.uid() = user_id);
CREATE POLICY "Users can delete own sessions"
  ON sessions FOR DELETE USING (auth.uid() = user_id);

-- Agent Tasks
CREATE POLICY "Users can view own agent tasks"
  ON agent_tasks FOR SELECT USING (auth.uid() = user_id);
CREATE POLICY "Users can insert own agent tasks"
  ON agent_tasks FOR INSERT WITH CHECK (auth.uid() = user_id);

-- ============================================================
-- INDEXES
-- ============================================================

CREATE INDEX idx_learning_goals_user_id ON learning_goals(user_id);
CREATE INDEX idx_prerequisites_goal_id ON prerequisites(goal_id);
CREATE INDEX idx_courses_goal_id ON courses(goal_id);
CREATE INDEX idx_courses_user_id ON courses(user_id);
CREATE INDEX idx_lessons_course_id ON lessons(course_id);
CREATE INDEX idx_sessions_user_id ON sessions(user_id);
CREATE INDEX idx_agent_tasks_goal_id ON agent_tasks(goal_id);
CREATE INDEX idx_agent_tasks_user_id ON agent_tasks(user_id);

-- ============================================================
-- REALTIME (enable for agent_tasks so UI can subscribe)
-- ============================================================

ALTER PUBLICATION supabase_realtime ADD TABLE agent_tasks;
