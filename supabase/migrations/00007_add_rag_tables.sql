-- RAG pipeline tables: sections, chunks with embeddings, figures, hybrid search function

-- Document sections (parsed structure)
CREATE TABLE resource_sections (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  resource_id UUID NOT NULL REFERENCES user_resources(id) ON DELETE CASCADE,
  user_id UUID NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
  goal_id UUID NOT NULL REFERENCES learning_goals(id) ON DELETE CASCADE,
  title TEXT NOT NULL,
  level INTEGER NOT NULL DEFAULT 1,
  path TEXT NOT NULL DEFAULT '',
  content TEXT,
  page_start INTEGER,
  page_end INTEGER,
  is_relevant BOOLEAN DEFAULT TRUE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_resource_sections_resource_id ON resource_sections(resource_id);
CREATE INDEX idx_resource_sections_goal_id ON resource_sections(goal_id);
ALTER TABLE resource_sections ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can view own sections"
  ON resource_sections FOR SELECT USING (auth.uid() = user_id);
CREATE POLICY "Users can insert own sections"
  ON resource_sections FOR INSERT WITH CHECK (auth.uid() = user_id);
CREATE POLICY "Users can delete own sections"
  ON resource_sections FOR DELETE USING (auth.uid() = user_id);

-- Document chunks with vector embeddings
CREATE TABLE resource_chunks (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  resource_id UUID NOT NULL REFERENCES user_resources(id) ON DELETE CASCADE,
  section_id UUID REFERENCES resource_sections(id) ON DELETE CASCADE,
  user_id UUID NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
  goal_id UUID NOT NULL REFERENCES learning_goals(id) ON DELETE CASCADE,
  content TEXT NOT NULL,
  context_prefix TEXT NOT NULL DEFAULT '',
  chunk_index INTEGER NOT NULL DEFAULT 0,
  token_count INTEGER NOT NULL DEFAULT 0,
  page_number INTEGER,
  embedding extensions.vector(768),
  content_tsv TSVECTOR GENERATED ALWAYS AS (to_tsvector('english', content)) STORED,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_resource_chunks_resource_id ON resource_chunks(resource_id);
CREATE INDEX idx_resource_chunks_goal_id ON resource_chunks(goal_id);
CREATE INDEX idx_resource_chunks_embedding ON resource_chunks
  USING hnsw (embedding extensions.vector_cosine_ops) WITH (m = 16, ef_construction = 64);
CREATE INDEX idx_resource_chunks_tsv ON resource_chunks USING gin (content_tsv);
ALTER TABLE resource_chunks ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can view own chunks"
  ON resource_chunks FOR SELECT USING (auth.uid() = user_id);
CREATE POLICY "Users can insert own chunks"
  ON resource_chunks FOR INSERT WITH CHECK (auth.uid() = user_id);
CREATE POLICY "Users can delete own chunks"
  ON resource_chunks FOR DELETE USING (auth.uid() = user_id);

-- Extracted figures/images
CREATE TABLE resource_figures (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  resource_id UUID NOT NULL REFERENCES user_resources(id) ON DELETE CASCADE,
  user_id UUID NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
  goal_id UUID NOT NULL REFERENCES learning_goals(id) ON DELETE CASCADE,
  storage_path TEXT NOT NULL,
  page_number INTEGER,
  caption TEXT,
  figure_type TEXT DEFAULT 'diagram',
  description TEXT,
  concepts TEXT[] DEFAULT '{}',
  description_embedding extensions.vector(768),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_resource_figures_resource_id ON resource_figures(resource_id);
CREATE INDEX idx_resource_figures_goal_id ON resource_figures(goal_id);
ALTER TABLE resource_figures ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can view own figures"
  ON resource_figures FOR SELECT USING (auth.uid() = user_id);
CREATE POLICY "Users can insert own figures"
  ON resource_figures FOR INSERT WITH CHECK (auth.uid() = user_id);
CREATE POLICY "Users can delete own figures"
  ON resource_figures FOR DELETE USING (auth.uid() = user_id);

-- Hybrid search function: RRF fusion of vector similarity + full-text search
CREATE OR REPLACE FUNCTION hybrid_search(
  query_embedding extensions.vector(768),
  query_text TEXT,
  p_goal_id UUID,
  p_user_id UUID,
  match_count INTEGER DEFAULT 10,
  vector_weight FLOAT DEFAULT 0.5,
  text_weight FLOAT DEFAULT 0.5,
  similarity_threshold FLOAT DEFAULT 0.3
)
RETURNS TABLE (
  chunk_id UUID,
  content TEXT,
  context_prefix TEXT,
  page_number INTEGER,
  resource_id UUID,
  file_name TEXT,
  similarity_score FLOAT,
  text_rank FLOAT,
  rrf_score FLOAT
)
LANGUAGE plpgsql
AS $$
DECLARE
  k CONSTANT INTEGER := 60;  -- RRF constant
BEGIN
  RETURN QUERY
  WITH vector_results AS (
    SELECT
      c.id,
      c.content,
      c.context_prefix,
      c.page_number,
      c.resource_id,
      1 - (c.embedding <=> query_embedding) AS vscore,
      ROW_NUMBER() OVER (ORDER BY c.embedding <=> query_embedding) AS vrank
    FROM resource_chunks c
    WHERE c.goal_id = p_goal_id
      AND c.user_id = p_user_id
      AND c.embedding IS NOT NULL
      AND 1 - (c.embedding <=> query_embedding) >= similarity_threshold
    ORDER BY c.embedding <=> query_embedding
    LIMIT match_count * 2
  ),
  text_results AS (
    SELECT
      c.id,
      c.content,
      c.context_prefix,
      c.page_number,
      c.resource_id,
      ts_rank_cd(c.content_tsv, websearch_to_tsquery('english', query_text)) AS tscore,
      ROW_NUMBER() OVER (ORDER BY ts_rank_cd(c.content_tsv, websearch_to_tsquery('english', query_text)) DESC) AS trank
    FROM resource_chunks c
    WHERE c.goal_id = p_goal_id
      AND c.user_id = p_user_id
      AND c.content_tsv @@ websearch_to_tsquery('english', query_text)
    ORDER BY tscore DESC
    LIMIT match_count * 2
  ),
  combined AS (
    SELECT
      COALESCE(v.id, t.id) AS id,
      COALESCE(v.content, t.content) AS content,
      COALESCE(v.context_prefix, t.context_prefix) AS context_prefix,
      COALESCE(v.page_number, t.page_number) AS page_number,
      COALESCE(v.resource_id, t.resource_id) AS resource_id,
      COALESCE(v.vscore, 0) AS vscore,
      COALESCE(t.tscore, 0) AS tscore,
      vector_weight * (1.0 / (k + COALESCE(v.vrank, match_count * 2 + 1)))
        + text_weight * (1.0 / (k + COALESCE(t.trank, match_count * 2 + 1))) AS combined_rrf
    FROM vector_results v
    FULL OUTER JOIN text_results t ON v.id = t.id
  )
  SELECT
    combined.id AS chunk_id,
    combined.content,
    combined.context_prefix,
    combined.page_number,
    combined.resource_id,
    ur.file_name,
    combined.vscore::FLOAT AS similarity_score,
    combined.tscore::FLOAT AS text_rank,
    combined.combined_rrf::FLOAT AS rrf_score
  FROM combined
  JOIN user_resources ur ON ur.id = combined.resource_id
  ORDER BY combined.combined_rrf DESC
  LIMIT match_count;
END;
$$;
