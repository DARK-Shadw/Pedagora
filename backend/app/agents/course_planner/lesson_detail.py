"""Stage 2: Generate detailed teaching DAG for a single lesson."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.agents.model_pool import ModelPool

from pydantic_ai import Agent

from app.agents.course_planner.prompts import LESSON_DETAIL_SYSTEM_PROMPT
from app.agents.course_planner.resources import fetch_lesson_resources
from app.agents.models import create_model
from app.agents.retry import run_with_retry
from app.config import get_settings
from app.models.course_plan import LessonOutline, LessonPlan, ResourceReference

logger = logging.getLogger(__name__)


def _build_research_data_for_lesson(
    lesson: LessonOutline,
    research_sources: list[dict],
    research_results: dict,
) -> str:
    """Build the research data section for a single lesson's prompt."""
    synthesis = research_results.get("synthesis", {})
    teaching_notes = research_results.get("teaching_notes", {})

    lines = []

    # Filter sources by topics_covered
    topics = set(lesson.topics_covered)
    relevant_sources = [
        s for s in research_sources
        if s.get("topic_group", "") in topics
    ]

    # Sources with truncated summaries
    for s in relevant_sources[:6]:
        extracted = s.get("extracted_content", {}) or {}
        summary = extracted.get("detailed_summary", s.get("summary", ""))[:300]
        lines.append(f"[{s.get('source_type', 'article')}] {s.get('title', 'Untitled')}")
        lines.append(f"  Summary: {summary}")

        # Formulas (top 3)
        formulas = s.get("formulas", [])
        for f in formulas[:3]:
            lines.append(
                f"  Formula: {f.get('description', '')}: "
                f"LaTeX: {f.get('latex', '')} | "
                f"Plain: {f.get('plain_text', '')}"
            )
            variables = f.get("variables", {})
            if variables:
                var_str = ", ".join(f"{k}={v}" for k, v in list(variables.items())[:5])
                lines.append(f"    Variables: {var_str}")

        # Code snippets (top 3, longer for animation reference_code)
        code_snippets = s.get("code_snippets", [])
        for cs in code_snippets[:3]:
            lines.append(
                f"  Code [{cs.get('language', '?')}]: {cs.get('description', '')[:150]}"
            )
            code_preview = cs.get("code", "")[:500]
            if code_preview:
                lines.append(f"    ```\n    {code_preview}\n    ```")

        # Numerical examples (for animation reference_values)
        numerical = extracted.get("numerical_examples", [])
        for n in numerical[:3]:
            lines.append(f"  Numerical: {n.get('description', '')[:120]}")
            if n.get("values"):
                lines.append(f"    Values: {n['values']}")

        # Misconceptions and analogies from extracted content
        misconceptions = extracted.get("misconceptions", [])
        for m in misconceptions[:2]:
            lines.append(f"  Misconception: {m.get('misconception', '')} → {m.get('correction', '')}")

        analogies = extracted.get("analogies", [])
        for a in analogies[:2]:
            lines.append(f"  Analogy: {a.get('analogy', '')[:150]}")

        lines.append("")

    # Teaching notes for relevant topics
    for topic in lesson.topics_covered:
        notes = teaching_notes.get(topic, "")
        if notes:
            lines.append(f"Teaching notes for {topic}: {notes[:200]}")

    # Exercises from synthesis
    exercises = synthesis.get("coding_exercises", [])
    relevant_exercises = [
        e for e in exercises
        if any(t.lower() in e.get("title", "").lower() for t in lesson.topics_covered)
    ]
    for ex in relevant_exercises[:2]:
        lines.append(
            f"Exercise: {ex.get('title', '')} [{ex.get('difficulty', '?')}] "
            f"— {ex.get('description', '')[:150]}"
        )
        if ex.get("starter_code"):
            lines.append(f"  Starter code: {ex['starter_code'][:200]}")

    return "\n".join(lines) if lines else "No research data available for this lesson."


def _build_student_resources_section(
    resource_refs: list[ResourceReference],
) -> str:
    """Format student resource references for the prompt."""
    if not resource_refs:
        return "No student resources uploaded for this goal."

    lines = ["The student has uploaded the following materials:"]
    for ref in resource_refs:
        line = f"- {ref.file_name}"
        if ref.page_number:
            line += f" (page {ref.page_number})"
        if ref.section_title:
            line += f" — section: {ref.section_title}"
        if ref.quote_snippet:
            line += f'\n  Content: "{ref.quote_snippet}..."'
        lines.append(line)

    return "\n".join(lines)


async def run_lesson_detail(
    lesson: LessonOutline,
    research_sources: list[dict],
    research_results: dict,
    onboarding_data: dict,
    goal_id: str,
    user_id: str,
    model_string: str | None = None,
) -> tuple[LessonPlan, list[ResourceReference]]:
    """Generate the full teaching DAG for a single lesson.

    Returns (LessonPlan, list of ResourceReferences used).
    """
    settings = get_settings()
    effective_model = model_string or settings.planner_detail_model
    goal = onboarding_data["goal"]
    preferences = onboarding_data.get("preferences", {})
    profile = onboarding_data.get("profile", {})

    # Fetch student resources via hybrid_search
    resource_refs = await fetch_lesson_resources(
        lesson_title=lesson.title,
        topics_covered=lesson.topics_covered,
        goal_id=goal_id,
        user_id=user_id,
    )

    # Build the prompt
    research_data = _build_research_data_for_lesson(
        lesson, research_sources, research_results,
    )
    student_resources = _build_student_resources_section(resource_refs)

    system_prompt = LESSON_DETAIL_SYSTEM_PROMPT.format(
        goal_title=goal.get("title", ""),
        education_level=profile.get("education_level", "self_learner"),
        learning_style=preferences.get("learning_style", "balanced"),
        lesson_title=lesson.title,
        lesson_id=lesson.lesson_id,
        lesson_type=lesson.lesson_type,
        estimated_minutes=lesson.estimated_minutes,
        estimated_seconds=lesson.estimated_minutes * 60,
        learning_objectives="; ".join(lesson.learning_objectives),
        topics_covered=", ".join(lesson.topics_covered),
        research_data=research_data,
        student_resources=student_resources,
    )

    agent = Agent(
        create_model(effective_model),
        system_prompt=system_prompt,
        output_type=LessonPlan,
        retries=3,
    )

    async def _run():
        result = await agent.run(
            f"Design the full teaching DAG for lesson: {lesson.title}"
        )
        plan = result.output
        # Ensure lesson_id matches
        plan.lesson_id = lesson.lesson_id
        plan.title = lesson.title
        # Reject shallow plans — triggers retry
        if len(plan.segments) < 8:
            raise ValueError(
                f"Lesson '{lesson.title}' produced only {len(plan.segments)} segments "
                f"(minimum 8 required)"
            )
        return plan

    lesson_plan = await run_with_retry(_run)

    # Post-processing: validate segment DAG integrity
    _validate_segment_dag(lesson_plan)

    # Count totals
    lesson_plan.total_animations = sum(
        len(seg.animations) for seg in lesson_plan.segments
    )
    lesson_plan.total_interactions = sum(
        1 for seg in lesson_plan.segments if seg.interaction
    )

    logger.info(
        f"Lesson detail complete: '{lesson.title}' — "
        f"{len(lesson_plan.segments)} segments, "
        f"{lesson_plan.total_animations} animations, "
        f"{lesson_plan.total_interactions} interactions"
    )

    return lesson_plan, resource_refs


def _validate_segment_dag(lesson_plan: LessonPlan) -> None:
    """Validate and fix segment DAG references and ensure branching integrity."""
    valid_ids = {seg.segment_id for seg in lesson_plan.segments}

    for i, seg in enumerate(lesson_plan.segments):
        # Fix next_segment: invalid refs → point to next in list or None
        if seg.next_segment and seg.next_segment not in valid_ids:
            if i + 1 < len(lesson_plan.segments):
                seg.next_segment = lesson_plan.segments[i + 1].segment_id
            else:
                seg.next_segment = None

        # Ensure linear flow: if next_segment is missing, link to next segment
        if not seg.next_segment and i + 1 < len(lesson_plan.segments):
            seg.next_segment = lesson_plan.segments[i + 1].segment_id

        # Fix interaction branch refs
        if seg.interaction:
            # if_correct: must point to valid segment or next in list
            if not seg.interaction.if_correct or seg.interaction.if_correct not in valid_ids:
                if i + 1 < len(lesson_plan.segments):
                    seg.interaction.if_correct = lesson_plan.segments[i + 1].segment_id

            # if_wrong/if_confused: fix invalid refs but don't clear them
            if seg.interaction.if_wrong and seg.interaction.if_wrong not in valid_ids:
                # Try to find a clarify segment nearby
                clarify_id = f"{seg.segment_id}-clarify"
                if clarify_id in valid_ids:
                    seg.interaction.if_wrong = clarify_id
                else:
                    seg.interaction.if_wrong = ""

            if seg.interaction.if_confused and seg.interaction.if_confused not in valid_ids:
                simplify_id = f"{seg.segment_id}-simplify"
                if simplify_id in valid_ids:
                    seg.interaction.if_confused = simplify_id
                else:
                    seg.interaction.if_confused = ""

    # Log branching stats
    checks = [s for s in lesson_plan.segments if s.interaction]
    branched = sum(1 for s in checks if s.interaction.if_wrong)
    logger.debug(
        f"DAG validation: {len(checks)} checks, {branched} with wrong-branch"
    )
