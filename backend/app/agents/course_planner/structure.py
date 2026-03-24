"""Stage 1: Generate course structure (modules + lesson outlines) from research results."""

import logging

from pydantic_ai import Agent

from app.agents.course_planner.prompts import STRUCTURE_SYSTEM_PROMPT
from app.agents.models import create_model
from app.agents.retry import run_with_retry
from app.config import get_settings
from app.models.course_plan import CourseStructure

logger = logging.getLogger(__name__)


def _build_research_summary(research_results: dict) -> str:
    """Compact the research data into a prompt-friendly summary."""
    synthesis = research_results.get("synthesis", {})
    lines = []
    lines.append(f"Overall: {synthesis.get('overall_summary', 'N/A')}")
    lines.append(f"Difficulty: {synthesis.get('estimated_difficulty', 'N/A')}")
    lines.append(f"Sources: {research_results.get('source_count', 0)}")
    lines.append(f"Key themes: {', '.join(synthesis.get('key_themes', []))}")

    # Formula/exercise counts
    formulas = synthesis.get("cross_topic_formulas", [])
    exercises = synthesis.get("coding_exercises", [])
    codebases = synthesis.get("demo_codebases", [])
    lines.append(
        f"Content: {len(formulas)} cross-topic formulas, "
        f"{len(exercises)} exercises, {len(codebases)} demo codebases"
    )
    return "\n".join(lines)


def _build_learning_path(research_results: dict) -> str:
    """Format the recommended learning path."""
    synthesis = research_results.get("synthesis", {})
    path = synthesis.get("recommended_learning_path", [])
    if not path:
        return "No learning path available."
    lines = []
    for step in path:
        hours = step.get("estimated_hours", "?")
        lines.append(f"{step.get('order', '?')}. {step.get('topic', '')} (~{hours}h) — {step.get('reason', '')}")
    return "\n".join(lines)


def _build_topic_groups_summary(research_results: dict) -> str:
    """Summarize topic groups with content needs and teaching notes."""
    topic_tree = research_results.get("topic_tree", {})
    teaching_notes = research_results.get("teaching_notes", {})
    groups = topic_tree.get("topic_groups", [])

    lines = []
    for tg in groups:
        name = tg.get("name", "Unknown")
        needs = tg.get("content_needs", {})
        flags = []
        if needs.get("needs_formulas"):
            flags.append("formulas")
        if needs.get("needs_code_examples"):
            flags.append("code")
        if needs.get("needs_working_codebase"):
            flags.append("codebase")
        if needs.get("needs_conceptual_depth"):
            flags.append("depth")
        priority = needs.get("priority", "medium")

        line = f"- {name} [priority={priority}] needs: {', '.join(flags) or 'conceptual'}"
        notes = teaching_notes.get(name, "")
        if notes:
            line += f"\n  Teaching notes: {notes[:200]}"
        lines.append(line)

    return "\n".join(lines)


async def run_structure_stage(
    onboarding_data: dict,
    research_results: dict,
) -> CourseStructure:
    """Stage 1: Generate the course skeleton from research results."""
    settings = get_settings()
    goal = onboarding_data["goal"]
    preferences = onboarding_data.get("preferences", {})
    profile = onboarding_data.get("profile", {})

    # Calculate total estimated hours from learning path
    synthesis = research_results.get("synthesis", {})
    path = synthesis.get("recommended_learning_path", [])
    total_hours = sum(s.get("estimated_hours", 0) for s in path) or 10.0
    session_minutes = preferences.get("session_duration_minutes", 60)

    system_prompt = STRUCTURE_SYSTEM_PROMPT.format(
        goal_title=goal.get("title", ""),
        end_goal=goal.get("end_goal", "Not specified"),
        education_level=profile.get("education_level", "self_learner"),
        learning_style=preferences.get("learning_style", "balanced"),
        content_depth=preferences.get("content_depth", "intermediate"),
        session_duration_minutes=session_minutes,
        hours_per_week=preferences.get("hours_per_week", 10),
        research_summary=_build_research_summary(research_results),
        learning_path=_build_learning_path(research_results),
        topic_groups=_build_topic_groups_summary(research_results),
        total_estimated_hours=total_hours,
        total_estimated_minutes=int(total_hours * 60),
    )

    agent = Agent(
        create_model(settings.planner_structure_model),
        system_prompt=system_prompt,
        output_type=CourseStructure,
        retries=3,
    )

    async def _run():
        result = await agent.run(
            f"Design a course structure for: {goal.get('title', '')}"
        )
        return result.output

    structure = await run_with_retry(_run)

    # Validate: at least 1 module, at least 3 lessons total
    total_lessons = sum(len(m.lessons) for m in structure.modules)
    if not structure.modules:
        raise ValueError("Structure stage produced 0 modules")
    if total_lessons < 3:
        logger.warning(f"Structure produced only {total_lessons} lessons (expected ≥3)")

    # Ensure all lesson_ids are unique
    seen_ids: set[str] = set()
    for module in structure.modules:
        for lesson in module.lessons:
            if lesson.lesson_id in seen_ids:
                lesson.lesson_id = f"{module.module_id}-{lesson.lesson_id}"
            seen_ids.add(lesson.lesson_id)

    # Fix module ordering and estimated_minutes
    for i, module in enumerate(structure.modules):
        module.order = i + 1
        if not module.estimated_minutes:
            module.estimated_minutes = sum(
                les.estimated_minutes for les in module.lessons
            )

    # Fix total course time
    structure.total_estimated_minutes = sum(
        m.estimated_minutes for m in structure.modules
    )

    logger.info(
        f"Structure complete: {len(structure.modules)} modules, "
        f"{total_lessons} lessons, ~{structure.total_estimated_minutes}min"
    )
    return structure
