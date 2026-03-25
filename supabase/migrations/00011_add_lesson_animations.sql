-- Lesson Animations: tracks per-animation status for the Animation Agent
-- Each row = one animation spec from the course plan, rendered to MP4

CREATE TABLE lesson_animations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    goal_id UUID NOT NULL REFERENCES learning_goals(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    lesson_id TEXT NOT NULL,
    animation_id TEXT NOT NULL,
    animation_type TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    manim_code TEXT,
    output_path TEXT,
    output_url TEXT,
    error_log TEXT,
    retry_count INTEGER DEFAULT 0,
    render_time_seconds FLOAT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(goal_id, lesson_id, animation_id)
);

CREATE INDEX idx_lesson_animations_goal_lesson
    ON lesson_animations(goal_id, lesson_id);

ALTER TABLE lesson_animations ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can view own animations"
    ON lesson_animations FOR SELECT
    USING (auth.uid() = user_id);

CREATE POLICY "Service role can manage animations"
    ON lesson_animations FOR ALL
    USING (auth.role() = 'service_role');

ALTER PUBLICATION supabase_realtime ADD TABLE lesson_animations;
