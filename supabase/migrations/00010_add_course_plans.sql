-- Course Plans: structured output from the Course Planner Agent
-- Stores the complete teaching DAG (course structure + per-lesson detail)

CREATE TABLE course_plans (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  goal_id UUID NOT NULL UNIQUE REFERENCES learning_goals(id) ON DELETE CASCADE,
  user_id UUID NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
  course_structure JSONB NOT NULL DEFAULT '{}',
  lesson_plans JSONB NOT NULL DEFAULT '{}',
  student_resource_map JSONB NOT NULL DEFAULT '{}',
  generation_metadata JSONB NOT NULL DEFAULT '{}',
  total_lessons INTEGER NOT NULL DEFAULT 0,
  total_modules INTEGER NOT NULL DEFAULT 0,
  total_estimated_minutes INTEGER NOT NULL DEFAULT 0,
  version INTEGER NOT NULL DEFAULT 1,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Auto-update updated_at on row change
CREATE TRIGGER course_plans_updated_at
  BEFORE UPDATE ON course_plans
  FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE INDEX idx_course_plans_goal_id ON course_plans(goal_id);

-- Row-level security
ALTER TABLE course_plans ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can view own course plans"
  ON course_plans FOR SELECT
  USING (auth.uid() = user_id);

CREATE POLICY "Service role can manage course plans"
  ON course_plans FOR ALL
  USING (auth.role() = 'service_role');

-- Enable realtime so frontend receives updates
ALTER PUBLICATION supabase_realtime ADD TABLE course_plans;
