from typing import Literal

from pydantic import BaseModel, Field


# ─── Content Needs (what downstream agents require) ───


class ContentNeeds(BaseModel):
    """What downstream agents need from this topic."""

    needs_formulas: bool = False
    needs_numerical_data: bool = False
    needs_code_examples: bool = False
    needs_working_codebase: bool = False
    needs_conceptual_depth: bool = False
    priority: str = Field(default="medium", description="high, medium, low")


# ─── Extracted Knowledge Types ───


class MathFormula(BaseModel):
    """A mathematical formula or equation extracted from sources."""

    latex: str
    plain_text: str
    description: str
    variables: dict[str, str] = {}
    context: str = ""


class NumericalExample(BaseModel):
    """Concrete numerical data for visualization."""

    description: str
    values: dict[str, str | float] = {}
    source_url: str = ""
    context: str = ""


class CodeSnippet(BaseModel):
    """Extracted or referenced code."""

    language: str
    code: str = Field(description="Actual code content (up to 2000 chars)")
    description: str
    source_url: str = ""
    source_repo: str | None = None
    runnable: bool = False
    dependencies: list[str] = []


class CodebaseReference(BaseModel):
    """Reference to a full working codebase for demos."""

    repo_url: str
    repo_name: str
    stars: int = 0
    description: str = ""
    main_language: str = ""
    key_files: list[str] = []
    setup_instructions: str = ""
    architecture_summary: str = ""
    suitability_score: float = Field(
        default=0.5, ge=0, le=1, description="How suitable for teaching/demo"
    )


class Misconception(BaseModel):
    """Common misconceptions about a topic."""

    misconception: str
    correction: str
    why_common: str = ""


class Analogy(BaseModel):
    """Teaching analogies for complex concepts."""

    concept: str
    analogy: str
    limitations: str = ""


class CodingExercise(BaseModel):
    """A coding exercise for live sessions."""

    title: str
    difficulty: str = Field(description="beginner, intermediate, advanced")
    description: str
    starter_code: str = ""
    expected_output: str | None = None
    hints: list[str] = []
    concepts_tested: list[str] = []


class ExtractedContent(BaseModel):
    """Deep content extracted from a single source."""

    source_url: str = ""
    key_concepts: list[str] = []
    detailed_summary: str = Field(
        default="", description="200-500 word deep summary"
    )
    formulas: list[MathFormula] = []
    numerical_examples: list[NumericalExample] = []
    code_snippets: list[CodeSnippet] = []
    misconceptions: list[Misconception] = []
    analogies: list[Analogy] = []
    prerequisites_mentioned: list[str] = []
    difficulty_level: str = "intermediate"


# ─── Search & Decomposition Models ───


class SearchQuery(BaseModel):
    query: str
    search_type: str = Field(description="One of: web, scholar, github")


class TopicGroup(BaseModel):
    name: str = Field(description="Name of the topic group")
    description: str = Field(
        description="Brief description of what this group covers"
    )
    importance: str = Field(
        description="Why this topic group matters for the learning goal"
    )
    search_queries: list[SearchQuery] = Field(
        description="2-4 search queries to find resources for this topic group"
    )
    order: int = Field(description="Suggested learning order (1 = first)")
    content_needs: ContentNeeds = Field(
        default_factory=ContentNeeds,
        description="What downstream agents need from this topic",
    )


class TopicTree(BaseModel):
    goal_summary: str = Field(
        description="One-sentence summary of the learning goal"
    )
    effort_tier: Literal["light", "standard", "deep"] = Field(
        default="standard",
        description="Research effort level based on goal complexity",
    )
    effort_rationale: str = Field(
        default="",
        description="Brief explanation of why this effort tier was chosen",
    )
    topic_groups: list[TopicGroup] = Field(
        description="Topic groups covering the full scope of the goal"
    )
    prerequisite_chain: list[str] = Field(
        description="Ordered list of prerequisites the student should know"
    )


# ─── Source & Research Results ───


class SourceInfo(BaseModel):
    topic_group: str = Field(
        description="Which topic group this source belongs to"
    )
    source_type: str = Field(
        description="article, paper, repo, tutorial, video, docs"
    )
    title: str
    url: str
    author: str | None = None
    summary: str = Field(
        description="Why this source is valuable for the learning goal"
    )
    key_concepts: list[str] = Field(
        description="Key concepts covered by this source"
    )
    relevance_score: float = Field(
        ge=0, le=1, description="How relevant to the goal (0-1)"
    )
    credibility_score: float = Field(
        ge=0, le=1, description="Source credibility (0-1)"
    )
    content_extract: str | None = Field(
        default=None, description="Key passage or takeaway from the source"
    )
    extracted_content: ExtractedContent | None = Field(
        default=None, description="Deep structured content from the source"
    )


class TopicResearchResult(BaseModel):
    topic_group: str
    sources: list[SourceInfo]
    notes: str = Field(
        description="Brief summary of what was found for this topic"
    )
    codebase_references: list[CodebaseReference] = []
    coding_exercises: list[CodingExercise] = []
    topic_formulas: list[MathFormula] = []
    topic_numerical_data: list[NumericalExample] = []


# ─── Synthesis Models ───


class SynthesisGap(BaseModel):
    topic: str
    description: str
    severity: str = Field(
        default="minor", description="critical, moderate, minor"
    )
    missing_content_type: str = Field(
        default="",
        description="What type of content is missing (formulas, code, concepts, etc.)",
    )


class LearningPathStep(BaseModel):
    order: int
    topic: str
    reason: str
    estimated_hours: float = Field(
        default=0, description="Estimated study hours for this topic"
    )


class ResearchSynthesis(BaseModel):
    overall_summary: str = Field(
        description="High-level summary of all research findings"
    )
    recommended_learning_path: list[LearningPathStep] = Field(
        description="Recommended order to study the topics"
    )
    key_themes: list[str] = Field(
        description="Cross-cutting themes found across sources"
    )
    gaps_identified: list[SynthesisGap] = Field(
        description="Topics where insufficient sources were found"
    )
    estimated_difficulty: str = Field(
        description="Overall difficulty assessment: beginner, intermediate, advanced"
    )
    total_sources: int
    teaching_notes: dict[str, str] = Field(
        default_factory=dict,
        description="Per-topic teaching guidance (topic_name -> notes)",
    )
    cross_topic_formulas: list[MathFormula] = Field(
        default_factory=list,
        description="Key formulas across all topics",
    )
    demo_codebases: list[CodebaseReference] = Field(
        default_factory=list,
        description="Best repos for building demos",
    )
    coding_exercises: list[CodingExercise] = Field(
        default_factory=list,
        description="Aggregated exercises organized by difficulty",
    )
