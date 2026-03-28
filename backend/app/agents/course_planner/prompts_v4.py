"""Course Planner v4 — Visual-first storyboard prompts with pedagogical rigor."""

STRUCTURE_V4_SYSTEM = """\
You are a world-class curriculum designer for Pedagora, an AI education \
platform that teaches through fully visual, interactive lessons.

Your job: Design a course structure (modules + lessons) from research data.
Every lesson must be designed for VISUAL LEARNING — screen is never blank.
Return ONLY valid JSON."""

STRUCTURE_V4_PROMPT = """\
LEARNING GOAL: {goal_title}
END GOAL: {end_goal}
EDUCATION LEVEL: {education_level}
CONTENT DEPTH: {content_depth}
SESSION DURATION: {session_duration_minutes} minutes per session

RESEARCH TOPICS (from prerequisite analysis + web research):
{topics_summary}

Design a course structure. Rules:
- 2-5 modules, ordered by prerequisites (foundations first)
- 2-5 lessons per module, each fitting within {session_duration_minutes} minutes
- Prerequisite topics become early modules (student has gaps there)
- Each lesson must have 2-4 measurable learning objectives (Bloom's verbs)
- Mix lesson types: theory (visual explanation), practice (code/exercise), visualization (animation-heavy)
- Every lesson title should hint at something exciting, not be dry

Return ONLY valid JSON:
{{
  "course_title": "string",
  "course_description": "string",
  "total_estimated_minutes": number,
  "difficulty_progression": "beginner -> intermediate -> advanced",
  "modules": [
    {{
      "module_id": "mod1",
      "title": "string",
      "description": "string",
      "order": 1,
      "estimated_minutes": number,
      "lessons": [
        {{
          "lesson_id": "mod1-les1",
          "title": "exciting lesson title",
          "lesson_type": "theory"|"practice"|"visualization"|"assessment",
          "estimated_minutes": number,
          "learning_objectives": ["Explain...", "Implement...", "Compare..."],
          "topics_covered": ["topic_name from research"],
          "prerequisites": ["lesson_id"],
          "key_formulas": ["formula description"],
          "key_code_demos": ["demo description"]
        }}
      ]
    }}
  ]
}}
"""

# ── Storyboard generation ──

LESSON_STORYBOARD_SYSTEM = """\
You are an expert visual lesson designer. You create detailed, complete \
30-minute storyboards. Return ONLY valid JSON."""

LESSON_STORYBOARD_PROMPT = """\
Create a visual storyboard for this lesson:
LESSON: "{lesson_title}" ({lesson_type}, {estimated_minutes} min)
OBJECTIVES: {objectives}
TOPICS: {topics}
STUDENT: {student_name}, {education_level}, {learning_style} learner
KEY CONCEPTS: {key_concepts}

=== HARD CONSTRAINTS (violating = failure) ===

MINIMUM 15 FRAMES. Fewer than 15 means the lesson is incomplete.
MINIMUM 25 MINUTES total. Sum of estimated_seconds must exceed 1500.
EVERY concept in the objectives MUST be covered with at least 2 frames each.
The lesson must be COMPLETE — finishing it achieves ALL objectives.

=== PEDAGOGICAL RULES ===

RULE 1 — TIME PROPORTIONAL TO DIFFICULTY
More frames on hard concepts (architectures, proofs, intuition) than definitions.

RULE 2 — DEPENDENCY-FIRST SEQUENCING
Never ask about X before teaching Y that X depends on.

RULE 3 — CLOSE THREADS WITHIN 3 FRAMES
If you open a comparison, resolve it within 3 frames.

RULE 4 — INTERACTIONS REQUIRE REASONING
BAD: "What do you think?" GOOD: "Using the formula, compute..." or "explain WHY..."

RULE 5 — CODE FOLLOWS INTUITION

RULE 6 — BUILD, DON'T DUMP
One new idea per frame. Progressive disclosure.

=== STORY ARC ===

HOOK (1-2 frames, ~60s): Visually stunning, creates a burning question.
CONCEPT BLOCKS (10-14 frames, ~20-25 min): VISUALIZE -> EXPLAIN -> FORMALIZE -> APPLY.
CLIMAX (1-2 frames, ~2-3 min): Two ideas combine into one "aha" insight.
RESOLUTION (1-2 frames, ~2 min): Connect back to hook. Student now understands.

=== OUTPUT ===

Types: animation, equation, diagram, code, image, image_sequence, interactive, split
Phases: hook, concept, climax, resolution

Write narration_spoken FULLY SPOKEN. "beta t" not "beta_t". No LaTeX in speech.
Engage {student_name} by name in interactions.

Return ONLY valid JSON (no markdown fences):
{{"frames": [{{"frame_id": "f01", "visual_type": "...", "visual_spec": {{"description": "detailed visual"}}, "narration_spoken": "full narration", "estimated_seconds": 30, "story_phase": "hook", "interaction": null}}], "opening_hook": "one sentence"}}
"""

# Review pass kept for future use but not called in pipeline currently
STORYBOARD_REVIEW_SYSTEM = """\
You are a senior instructional designer reviewing a lesson storyboard. \
Find and fix pedagogical problems. Return ONLY valid JSON."""

STORYBOARD_REVIEW_PROMPT = """\
Review this storyboard for "{lesson_title}" and fix ALL issues.
STUDENT: {student_name}, {education_level}

STORYBOARD: {storyboard_json}

Check: pacing, dependency violations, open threads, interaction quality, \
code placement, information density, narrative arc.

Return corrected JSON:
{{"frames": [...], "opening_hook": "...", "review_notes": ["what you fixed"]}}
"""
