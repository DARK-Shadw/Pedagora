-- Teaching sessions: persistent state for live AI teacher lessons
-- Tracks progress through the teaching DAG, student scores, dialogue history

CREATE TABLE teaching_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    goal_id UUID NOT NULL REFERENCES learning_goals(id) ON DELETE CASCADE,
    lesson_id TEXT NOT NULL,
    user_id UUID NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    status TEXT NOT NULL DEFAULT 'active',  -- active, paused, completed
    current_segment_id TEXT,
    dialogue_state JSONB NOT NULL DEFAULT '{}',
    student_scores JSONB NOT NULL DEFAULT '{}',
    session_summary JSONB,
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_active_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TRIGGER teaching_sessions_updated_at
  BEFORE UPDATE ON teaching_sessions
  FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE INDEX idx_teaching_sessions_user ON teaching_sessions(user_id);
CREATE INDEX idx_teaching_sessions_goal_lesson ON teaching_sessions(goal_id, lesson_id);

ALTER TABLE teaching_sessions ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can view own teaching sessions"
  ON teaching_sessions FOR SELECT
  USING (auth.uid() = user_id);

CREATE POLICY "Service role can manage teaching sessions"
  ON teaching_sessions FOR ALL
  USING (auth.role() = 'service_role');

ALTER PUBLICATION supabase_realtime ADD TABLE teaching_sessions;

-- Shareable lesson links: anyone with the code can start a fresh session
CREATE TABLE lesson_links (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    goal_id UUID NOT NULL REFERENCES learning_goals(id) ON DELETE CASCADE,
    lesson_id TEXT NOT NULL,
    share_code TEXT UNIQUE NOT NULL,
    created_by UUID NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    is_active BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_lesson_links_code ON lesson_links(share_code);

ALTER TABLE lesson_links ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can view own lesson links"
  ON lesson_links FOR SELECT
  USING (auth.uid() = created_by);

CREATE POLICY "Anyone can resolve active links"
  ON lesson_links FOR SELECT
  USING (is_active = true);

CREATE POLICY "Service role can manage lesson links"
  ON lesson_links FOR ALL
  USING (auth.role() = 'service_role');
