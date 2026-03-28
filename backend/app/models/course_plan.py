"""Pydantic models for the Course Planner Agent output.

Two-stage output:
  Stage 1 → CourseStructure (course skeleton: modules + lesson outlines)
  Stage 2 → LessonPlan (per-lesson teaching DAG with segments, animations, interactions)
"""

from typing import Literal

from pydantic import BaseModel, Field


# ─── Stage 1: Course Structure ───


class LessonOutline(BaseModel):
    """Lightweight lesson descriptor produced by Stage 1."""

    lesson_id: str = Field(description="Unique slug e.g. 'mod1-les2'")
    title: str
    lesson_type: Literal["theory", "practice", "visualization", "assessment"] = "theory"
    estimated_minutes: int = Field(default=30, ge=5, le=120)
    learning_objectives: list[str] = Field(
        default_factory=list,
        description="2-4 measurable objectives (Bloom's taxonomy verbs)",
    )
    topics_covered: list[str] = Field(
        default_factory=list,
        description="Which research topic_groups this lesson draws from",
    )
    prerequisites: list[str] = Field(
        default_factory=list,
        description="lesson_ids that must be completed first",
    )
    key_formulas: list[str] = Field(
        default_factory=list,
        description="Formula descriptions from research to include",
    )
    key_code_demos: list[str] = Field(
        default_factory=list,
        description="Code demo descriptions from research",
    )


class ModuleOutline(BaseModel):
    """A group of related lessons."""

    module_id: str = Field(description="e.g. 'mod1'")
    title: str
    description: str = ""
    order: int = 1
    estimated_minutes: int = 0
    lessons: list[LessonOutline] = Field(default_factory=list)


class CourseStructure(BaseModel):
    """Stage 1 output: the structural skeleton of the course."""

    course_title: str
    course_description: str = ""
    total_estimated_minutes: int = 0
    difficulty_progression: str = Field(
        default="beginner -> intermediate",
        description="e.g. 'beginner -> intermediate -> advanced'",
    )
    modules: list[ModuleOutline] = Field(default_factory=list)


# ─── Stage 2: Lesson Detail (Teaching DAG) ───


class FormulaRevealStep(BaseModel):
    """One step in piece-by-piece formula reveal."""

    component: str = Field(description="e.g. 'μ (mu)'")
    explanation: str = Field(description="What this component means and why")
    latex_fragment: str = ""


class FormulaTeachingSpec(BaseModel):
    """How to teach a specific formula."""

    formula_latex: str
    formula_plain: str = ""
    context: str = Field(default="", description="When/why this formula is used")
    reveal_steps: list[FormulaRevealStep] = Field(default_factory=list)
    variables: dict[str, str] = Field(default_factory=dict)


class AnimationSpec(BaseModel):
    """Spec for Animation Agent to pre-generate a visual."""

    animation_id: str = Field(description="e.g. 'seg2-anim1'")
    animation_type: str = Field(
        default="diagram_build",
        description="equation_reveal, diagram_build, graph_plot, code_walkthrough, "
        "comparison, process_flow, 3d_visualization, data_animation",
    )
    title: str = ""
    description: str = Field(
        default="",
        description="Detailed natural-language description of what to show — "
        "must be self-contained for Animation Agent",
    )
    parameters: dict[str, str | float | int | list] = Field(default_factory=dict)
    duration_seconds: float = Field(default=10.0, ge=2.0, le=60.0)
    trigger: Literal["auto", "on_teacher_cue", "on_student_request"] = "auto"

    # Research data passthrough for Animation Agent
    reference_code: str = Field(
        default="",
        description="Code snippet from research that implements this concept",
    )
    reference_formula_latex: str = Field(
        default="",
        description="LaTeX formula being visualized",
    )
    reference_formula_vars: dict[str, str] = Field(
        default_factory=dict,
        description="Variable names and descriptions from the formula",
    )
    reference_values: dict[str, str | float | int] = Field(
        default_factory=dict,
        description="Numerical values from research (lr, batch_size, timesteps, etc.)",
    )
    data_requirements: str = Field(
        default="",
        description="What data the animation needs: 'MNIST digit', '8-frame video clip', etc.",
    )


class ResourceReference(BaseModel):
    """Reference to student's uploaded material."""

    file_name: str = ""
    page_number: int | None = None
    section_title: str = ""
    quote_snippet: str = Field(
        default="",
        description="Short excerpt the teacher can read aloud",
    )
    relevance_note: str = ""


class InteractionSpec(BaseModel):
    """A CHECK_UNDERSTANDING branching node."""

    question: str
    question_type: Literal["conceptual", "calculation", "code_output", "true_false"] = "conceptual"
    expected_answer: str = ""
    answer_explanation: str = ""
    if_correct: str = Field(default="", description="Next segment_id to proceed to")
    if_wrong: str = Field(default="", description="Segment_id for clarification branch")
    if_confused: str = Field(default="", description="Segment_id for simplified re-explanation")
    hints: list[str] = Field(default_factory=list)


class CodeDemoSpec(BaseModel):
    """A code demonstration with modifiable parameters."""

    language: str = "python"
    code: str = Field(default="", description="Full runnable code")
    description: str = ""
    parameters_to_modify: list[dict[str, str]] = Field(
        default_factory=list,
        description="[{'name': 'lr', 'current': '0.001', 'try_values': '0.01, 0.1'}]",
    )
    expected_output: str = ""


class TeachingSegment(BaseModel):
    """A single segment within a lesson — the atomic unit of the teaching DAG.

    This is a flat union: segment_type determines which fields are populated.
    Free-tier LLMs handle flat models with optional fields far more reliably
    than deeply nested discriminated unions.
    """

    segment_id: str = Field(description="e.g. 'seg1', 'seg2-clarify'")
    segment_type: Literal[
        "TEACH", "DEMONSTRATE", "CHECK_UNDERSTANDING", "PRACTICE", "TRANSITION",
    ]
    title: str = ""
    estimated_seconds: int = Field(default=120, ge=10, le=600)
    next_segment: str | None = Field(
        default=None, description="Default next segment_id (linear flow)",
    )

    # TEACH fields
    key_points: list[str] = Field(default_factory=list)
    formulas: list[FormulaTeachingSpec] = Field(default_factory=list)
    analogies: list[str] = Field(default_factory=list)
    misconceptions_to_address: list[str] = Field(default_factory=list)
    resource_references: list[ResourceReference] = Field(default_factory=list)

    # DEMONSTRATE fields
    code_demos: list[CodeDemoSpec] = Field(default_factory=list)

    # CHECK_UNDERSTANDING fields
    interaction: InteractionSpec | None = None

    # PRACTICE fields
    exercise_title: str = ""
    exercise_description: str = ""
    starter_code: str = ""
    exercise_hints: list[str] = Field(default_factory=list)

    # TRANSITION fields
    bridge_text: str = ""

    # Animation specs (applicable to any segment type)
    animations: list[AnimationSpec] = Field(default_factory=list)


class LessonPlan(BaseModel):
    """Stage 2 output: full teaching DAG for a single lesson."""

    lesson_id: str
    title: str
    opening_hook: str = Field(
        default="", description="Attention-grabbing opening statement or question",
    )
    segments: list[TeachingSegment] = Field(default_factory=list)
    closing_summary: list[str] = Field(
        default_factory=list,
        description="3-5 bullet points summarizing what was learned",
    )
    total_animations: int = 0
    total_interactions: int = 0


# ─── Composite Storage Model ───


class CoursePlan(BaseModel):
    """Complete course plan combining structure + all lesson plans."""

    course_structure: CourseStructure = Field(default_factory=CourseStructure)
    lesson_plans: dict[str, LessonPlan] = Field(
        default_factory=dict,
        description="lesson_id -> LessonPlan",
    )
    student_resource_map: dict[str, list[ResourceReference]] = Field(
        default_factory=dict,
        description="lesson_id -> relevant student resources",
    )
    generation_metadata: dict = Field(default_factory=dict)


# ─── v4: Visual-First Storyboard Models ───


class VisualStep(BaseModel):
    """A sub-step within a visual frame (e.g., one line of equation reveal)."""

    step_id: str = Field(description="e.g. 'step-1'")
    label: str = Field(description="GSAP timeline label for seeking")
    description: str = Field(description="What changes visually at this step")
    narration: str = Field(description="What teacher says during this step")
    narration_spoken: str = Field(description="TTS-friendly, no math notation")
    duration_seconds: float = Field(default=3.0)
    pause_after: bool = Field(default=False, description="Teacher pauses here for emphasis")


class FrameInteraction(BaseModel):
    """Student engagement point within a frame."""

    interaction_type: Literal["predict", "question", "opinion", "manipulate", "fill_blank"]
    prompt: str = Field(description="What teacher asks the student")
    expected_response: str | None = None
    hints: list[str] = Field(default_factory=list)
    on_correct: str | None = Field(default=None, description="Frame ID to go to if correct")
    on_wrong: str | None = None
    on_skip: str | None = None


class VisualFrame(BaseModel):
    """One visual state on screen + narration + optional interaction.

    The core unit of v4 storyboards. Each lesson is a sequence of frames.
    """

    frame_id: str = Field(description="e.g. 'les1-f01'")
    visual_type: Literal[
        "animation",        # Manim step-based animation
        "equation",         # KaTeX with step-by-step reveal
        "diagram",          # SVG diagram building up
        "code",             # Syntax-highlighted code with line reveal
        "image",            # Static image (paper figure, example output)
        "image_sequence",   # Series of images (noise progression)
        "interactive",      # Student can manipulate parameters
        "split",            # Two visuals side-by-side (comparison)
        "blackboard",       # Empty canvas for teacher drawing
    ]

    # What's on screen
    visual_spec: dict = Field(description="Type-specific rendering specification")

    # What teacher says
    narration: str = Field(description="Pre-written narration script")
    narration_spoken: str = Field(description="TTS-friendly version, no math notation")

    # Timing
    estimated_seconds: int = Field(default=20, ge=5, le=300)
    transition: str = Field(default="fade")

    # Step control (for animations/equations with multiple steps)
    steps: list[VisualStep] = Field(default_factory=list)

    # Interaction
    interaction: FrameInteraction | None = None

    # Story position
    story_phase: Literal["hook", "motivation", "concept", "climax", "resolution", "practice"] = "concept"

    # Flow
    next_frame: str | None = None
