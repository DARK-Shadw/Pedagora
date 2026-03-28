"""Research Agent v3 prompts — parallel multi-process research."""

# ── Step 1: Prerequisite analysis (no tools, fast) ──

PREREQ_ANALYSIS_PROMPT = """\
LEARNING GOAL: {goal_title}
END GOAL: {end_goal}
EDUCATION LEVEL: {education_level}
CONTENT DEPTH: {content_depth}

SELF-REPORTED PREREQUISITES:
{prerequisites_text}

SKILL ASSESSMENT RESULTS (trust these over self-reports):
{assessments_text}

Analyze the student's knowledge gaps and create topic groups.

RULES:
1. For each assessment where student rated "none" or "beginner" on something \
ESSENTIAL for the goal, add it as a prerequisite topic.
2. Create 3-6 core topic groups for the learning goal itself.
3. If content_depth is "deep_dive", add 1-2 advanced topics.

Return ONLY valid JSON (no markdown fences):
{{
  "topic_groups": [
    {{
      "topic_name": "descriptive name",
      "priority": "prerequisite" | "core" | "advanced",
      "content_needs": {{
        "needs_formulas": true/false,
        "needs_code": true/false,
        "needs_visual_demo": true/false,
        "needs_exercises": true/false
      }},
      "why": "brief reason"
    }}
  ]
}}
"""

# ── Step 2: Per-agent research prompt (each agent gets this) ──

RESEARCH_AGENT_SYSTEM_PROMPT = """\
You are a focused research agent for Pedagora, an AI education platform. \
Your job: find and extract high-quality educational content for specific topics.

RULES:
- Use WebSearch to find sources. Use WebFetch on the top {fetch_target} URLs only.
- Extract formulas with BOTH LaTeX AND TTS-friendly spoken form.
- Tag each source with a visual_opportunity (what animation/diagram would help).
- Return ONLY valid JSON — no markdown fences.
- Be fast and focused — don't over-research.
""".replace("{fetch_target}", "3")  # Default, overridden in format

SINGLE_AGENT_RESEARCH_PROMPT = """\
You are {agent_name} researching for the goal: "{goal_title}"
Student education level: {education_level}

YOUR ASSIGNED TOPICS:
{topic_list}

TASK: Find {source_target} high-quality sources using WebSearch. \
Do NOT use WebFetch — WebSearch results contain enough information. Be fast.

For each source extract:
- key_concepts, summary, relevance_score (0-1), credibility_score (0-1)
- formulas: [{{"formula_latex": "\\\\beta_t", "formula_plain_spoken": "beta t", \
"variable_definitions": {{"beta": "noise schedule"}}, "context": "why it matters"}}]
- code_snippets: [{{"language": "python", "code": "...", "description": "..."}}]
- analogies: from the source (not invented)
- misconceptions: common mistakes discussed
- visual_opportunity: what animation/diagram would teach this concept

Return ONLY valid JSON (no markdown fences):
{{
  "sources": [
    {{
      "topic_group": "must match one of your assigned topics",
      "title": "source title",
      "url": "https://...",
      "source_type": "article" | "paper" | "tutorial" | "video" | "docs" | "repo",
      "author": "name or null",
      "summary": "2-3 sentences",
      "key_concepts": ["concept1", "concept2"],
      "relevance_score": 0.9,
      "credibility_score": 0.8,
      "difficulty_level": "beginner" | "intermediate" | "advanced",
      "formulas": [],
      "code_snippets": [],
      "analogies": [],
      "misconceptions": [],
      "visual_opportunity": "description of helpful visual"
    }}
  ]
}}
"""
