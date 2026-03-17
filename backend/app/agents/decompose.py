from pydantic_ai import Agent

from app.agents.models import create_model
from app.agents.prompts import DECOMPOSE_SYSTEM_PROMPT
from app.agents.retry import run_with_retry
from app.config import get_settings
from app.models.domain import TopicTree


async def run_decompose(onboarding_data: dict) -> TopicTree:
    """Stage 1: Decompose a learning goal into topic groups with search queries and content needs."""
    goal = onboarding_data["goal"]
    preferences = onboarding_data.get("preferences", {})
    profile = onboarding_data.get("profile", {})
    prerequisites = onboarding_data.get("prerequisites", [])

    known = [
        p["skill_name"]
        for p in prerequisites
        if p.get("confidence_level") in ("intermediate", "advanced")
    ]
    weak = [
        p["skill_name"]
        for p in prerequisites
        if p.get("confidence_level") in ("none", "beginner")
    ]

    system_prompt = DECOMPOSE_SYSTEM_PROMPT.format(
        goal_title=goal.get("title", ""),
        end_goal=goal.get("end_goal", "Not specified"),
        motivation=goal.get("motivation", "Not specified"),
        education_level=profile.get("education_level", "self_learner"),
        learning_style=preferences.get("learning_style", "balanced"),
        content_depth=preferences.get("content_depth", "intermediate"),
        known_prerequisites=", ".join(known) if known else "None specified",
        weak_areas=", ".join(weak) if weak else "None specified",
    )

    settings = get_settings()
    agent = Agent(
        create_model(settings.decompose_model),
        system_prompt=system_prompt,
        output_type=TopicTree,
    )

    async def _run():
        result = await agent.run(
            f"Decompose this learning goal into topic groups: {goal.get('title', '')}"
        )
        return result.output

    return await run_with_retry(_run)
