-- Research Agent v2: Add deep extraction columns to research_sources
ALTER TABLE research_sources ADD COLUMN IF NOT EXISTS extracted_content JSONB DEFAULT '{}';
ALTER TABLE research_sources ADD COLUMN IF NOT EXISTS formulas JSONB DEFAULT '[]';
ALTER TABLE research_sources ADD COLUMN IF NOT EXISTS code_snippets JSONB DEFAULT '[]';
ALTER TABLE research_sources ADD COLUMN IF NOT EXISTS numerical_examples JSONB DEFAULT '[]';
ALTER TABLE research_sources ADD COLUMN IF NOT EXISTS codebase_reference JSONB;
ALTER TABLE research_sources ADD COLUMN IF NOT EXISTS difficulty_level TEXT;

-- Research Agent v2: Add teaching data columns to research_results
ALTER TABLE research_results ADD COLUMN IF NOT EXISTS teaching_notes JSONB DEFAULT '{}';
ALTER TABLE research_results ADD COLUMN IF NOT EXISTS demo_codebases JSONB DEFAULT '[]';
ALTER TABLE research_results ADD COLUMN IF NOT EXISTS coding_exercises JSONB DEFAULT '[]';
ALTER TABLE research_results ADD COLUMN IF NOT EXISTS cross_topic_formulas JSONB DEFAULT '[]';
ALTER TABLE research_results ADD COLUMN IF NOT EXISTS version INTEGER DEFAULT 2;
