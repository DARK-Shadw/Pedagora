-- Research Sources: normalized sources (one row per source per topic group)
CREATE TABLE research_sources (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  goal_id UUID NOT NULL REFERENCES learning_goals(id) ON DELETE CASCADE,
  user_id UUID NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
  topic_group TEXT NOT NULL,
  source_type TEXT NOT NULL,
  title TEXT NOT NULL,
  url TEXT,
  author TEXT,
  summary TEXT,
  key_concepts TEXT[] NOT NULL DEFAULT '{}',
  relevance_score NUMERIC(3,2) DEFAULT 0,
  credibility_score NUMERIC(3,2) DEFAULT 0,
  content_extract TEXT,
  metadata JSONB NOT NULL DEFAULT '{}',
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_research_sources_goal_id ON research_sources(goal_id);
ALTER TABLE research_sources ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can view own research sources"
  ON research_sources FOR SELECT USING (auth.uid() = user_id);
-- Service role bypasses RLS, so no INSERT policy needed for backend

-- Research Results: full structured output per goal
CREATE TABLE research_results (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  goal_id UUID NOT NULL UNIQUE REFERENCES learning_goals(id) ON DELETE CASCADE,
  user_id UUID NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
  topic_tree JSONB NOT NULL DEFAULT '{}',
  synthesis JSONB NOT NULL DEFAULT '{}',
  source_count INTEGER NOT NULL DEFAULT 0,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TRIGGER research_results_updated_at
  BEFORE UPDATE ON research_results
  FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE INDEX idx_research_results_goal_id ON research_results(goal_id);
ALTER TABLE research_results ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can view own research results"
  ON research_results FOR SELECT USING (auth.uid() = user_id);
