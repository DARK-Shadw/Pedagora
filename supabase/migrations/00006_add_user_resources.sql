-- User resource uploads: stores metadata for uploaded study materials
CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA extensions;

CREATE TYPE resource_status AS ENUM ('uploaded', 'processing', 'ready', 'failed');

CREATE TABLE user_resources (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  goal_id UUID NOT NULL REFERENCES learning_goals(id) ON DELETE CASCADE,
  user_id UUID NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
  file_name TEXT NOT NULL,
  file_type TEXT NOT NULL,
  file_size_bytes BIGINT NOT NULL,
  storage_path TEXT NOT NULL,
  status resource_status NOT NULL DEFAULT 'uploaded',
  error_message TEXT,
  page_count INTEGER,
  toc_structure JSONB,
  relevant_sections JSONB,
  chunk_count INTEGER DEFAULT 0,
  figure_count INTEGER DEFAULT 0,
  processed_at TIMESTAMPTZ,
  expires_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TRIGGER user_resources_updated_at
  BEFORE UPDATE ON user_resources
  FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE INDEX idx_user_resources_goal_id ON user_resources(goal_id);
CREATE INDEX idx_user_resources_user_id ON user_resources(user_id);
ALTER TABLE user_resources ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can view own resources"
  ON user_resources FOR SELECT USING (auth.uid() = user_id);
CREATE POLICY "Users can insert own resources"
  ON user_resources FOR INSERT WITH CHECK (auth.uid() = user_id);
CREATE POLICY "Users can delete own resources"
  ON user_resources FOR DELETE USING (auth.uid() = user_id);
