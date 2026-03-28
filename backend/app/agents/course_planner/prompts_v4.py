"""Course Planner v4 — Visual-first storyboard prompts."""

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

RESEARCH TOPICS:
{topics_summary}

RESEARCH TEACHING NOTES:
{teaching_notes}

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

LESSON_STORYBOARD_SYSTEM = """\
You are a visual lesson storyboard creator for Pedagora. You create \
detailed frame-by-frame screenplays for fully visual, interactive lessons.

CRITICAL RULES:
- The screen is NEVER blank. Every frame has a visual.
- Follow the 3Blue1Brown story arc: Hook -> Motivation -> Concept Blocks -> Climax -> Resolution
- Visual change every 15-25 seconds (students lose focus otherwise)
- Use the Predict-Observe-Explain (POE) pattern for interactions
- Narration + visuals, NOT text + visuals (Mayer's modality principle)
- Max 3-4 elements on screen at once (Cowan's 4-chunk working memory limit)
- Visuals before abstraction: show the concrete example FIRST, then formalize
- "Definitions are endings, not beginnings" — show why it matters before naming it
- Write narration_spoken in fully spoken form: "beta t" not "beta_t", no LaTeX

Return ONLY valid JSON."""

LESSON_STORYBOARD_PROMPT = """\
LESSON: {lesson_title}
LESSON TYPE: {lesson_type}
DURATION: {estimated_minutes} minutes
LEARNING OBJECTIVES: {objectives}
TOPICS: {topics}

STUDENT PROFILE:
- Education: {education_level}
- Learning style: {learning_style}
- Name: {student_name}

RESEARCH DATA FOR THIS LESSON:
Formulas: {formulas}
Code snippets: {code_snippets}
Key concepts: {key_concepts}
Visual opportunities: {visual_opportunities}
Misconceptions: {misconceptions}
Analogies: {analogies}

Create a frame-by-frame visual storyboard. The lesson should have 15-30 frames \
following this story arc:

[HOOK] (1-2 frames, ~60s)
Start with something visually stunning or a surprising question. Make the student \
WANT to stay. Use an image, animation, or provocative question.

[MOTIVATION] (1-2 frames, ~60s)
Why does this matter? Show real-world examples. Connect to the student's goal.

[CONCEPT BLOCKS] (10-20 frames, ~20 min)
Each concept follows: VISUALIZE -> EXPLAIN -> FORMALIZE -> CHECK
- VISUALIZE: Show the concept with an animation or diagram FIRST
- EXPLAIN: Teacher narrates while visual plays, step by step
- FORMALIZE: Reveal the equation/formula piece by piece
- CHECK: Ask student a question (POE pattern preferred)

[CLIMAX] (2-3 frames, ~2 min)
The "aha moment" — where two concepts combine and everything clicks.

[RESOLUTION] (1-2 frames, ~60s)
Connect back to the hook. Show what the student now understands.

For EACH frame, specify:
- visual_type: "animation"|"equation"|"diagram"|"code"|"image"|"image_sequence"|"interactive"|"split"|"blackboard"
- visual_spec: detailed rendering specification (see examples below)
- narration: what the teacher says (conversational, uses student name occasionally)
- narration_spoken: TTS-friendly version (no math notation, no LaTeX)
- steps: for multi-step visuals (animations, equations), specify each step with a label
- interaction: if this frame has student engagement (predict/question/opinion)

VISUAL SPEC EXAMPLES:
- equation: {{"latex": "q(x_t|x_{{t-1}}) = ...", "highlight_steps": [{{"range": [0,15], "label": "lhs"}}]}}
- diagram: {{"elements": [{{"id":"enc","type":"box","label":"Encoder"}}], "build_order": ["enc"]}}
- image_sequence: {{"images": [{{"label":"t=0","description":"clean image"}}], "layout":"horizontal"}}
- code: {{"language":"python","code":"def forward(x, t):...","reveal":"line_by_line"}}
- animation: {{"scene":"ForwardDiffusion","steps":[{{"t":0,"description":"clean image"}}],"data_requirements":"MNIST"}}

Engage the student by name ({student_name}) in at least 3 interactions. Use the \
POE pattern: "What do you THINK happens when...?" -> show it -> "Here's WHY..."

Return ONLY valid JSON:
{{
  "frames": [
    {{
      "frame_id": "f01",
      "visual_type": "image",
      "visual_spec": {{}},
      "narration": "string",
      "narration_spoken": "string (TTS-friendly)",
      "estimated_seconds": 20,
      "transition": "fade",
      "story_phase": "hook"|"motivation"|"concept"|"climax"|"resolution"|"practice",
      "steps": [],
      "interaction": null | {{
        "interaction_type": "predict"|"question"|"opinion",
        "prompt": "string",
        "expected_response": "string or null",
        "hints": []
      }},
      "next_frame": "f02"
    }}
  ],
  "opening_hook": "string (1-sentence hook for lesson start)",
  "closing_summary": ["point 1", "point 2", "point 3"]
}}
"""
