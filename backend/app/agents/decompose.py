import logging

from pydantic_ai import Agent

from app.agents.effort import EFFORT_PROFILES, validate_effort_tier
from app.agents.models import create_model
from app.agents.prompts import DECOMPOSE_SYSTEM_PROMPT
from app.agents.retry import run_with_retry
from app.config import get_settings
from app.models.domain import TopicTree

logger = logging.getLogger(__name__)


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

    # Build effort profile format kwargs for the prompt
    effort_kwargs: dict[str, int] = {}
    for tier_name, profile_data in EFFORT_PROFILES.items():
        effort_kwargs[f"{tier_name}_topics_min"] = profile_data["topics_min"]
        effort_kwargs[f"{tier_name}_topics_max"] = profile_data["topics_max"]
        effort_kwargs[f"{tier_name}_queries_min"] = profile_data["queries_per_topic_min"]
        effort_kwargs[f"{tier_name}_queries_max"] = profile_data["queries_per_topic_max"]

    system_prompt = DECOMPOSE_SYSTEM_PROMPT.format(
        goal_title=goal.get("title", ""),
        end_goal=goal.get("end_goal", "Not specified"),
        motivation=goal.get("motivation", "Not specified"),
        education_level=profile.get("education_level", "self_learner"),
        learning_style=preferences.get("learning_style", "balanced"),
        content_depth=preferences.get("content_depth", "intermediate"),
        known_prerequisites=", ".join(known) if known else "None specified",
        weak_areas=", ".join(weak) if weak else "None specified",
        **effort_kwargs,
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

    topic_tree = await run_with_retry(_run)

    # Validate and normalize the effort tier (handles LLM hallucinations)
    topic_tree.effort_tier = validate_effort_tier(topic_tree.effort_tier)

    # Heuristic overrides: catch mismatches between tier and actual output
    num_topics = len(topic_tree.topic_groups)
    avg_queries = (
        sum(len(tg.search_queries) for tg in topic_tree.topic_groups) / max(num_topics, 1)
    )

    original_tier = topic_tree.effort_tier
    if topic_tree.effort_tier == "deep" and num_topics <= 3 and avg_queries <= 2:
        topic_tree.effort_tier = "standard"
        logger.info(
            f"Effort tier downgraded: deep -> standard "
            f"(only {num_topics} topics, avg {avg_queries:.1f} queries)"
        )
    elif topic_tree.effort_tier == "light" and num_topics >= 7:
        topic_tree.effort_tier = "standard"
        logger.info(
            f"Effort tier upgraded: light -> standard "
            f"({num_topics} topics produced)"
        )

    if topic_tree.effort_tier != original_tier:
        topic_tree.effort_rationale += (
            f" [Auto-adjusted from {original_tier} based on actual output]"
        )

    # Post-processing: filter out topics that overlap with known prerequisites
    if known:
        known_lower = {k.lower().strip() for k in known}
        original_count = len(topic_tree.topic_groups)
        filtered = []
        for tg in topic_tree.topic_groups:
            topic_lower = tg.name.lower().strip()
            is_prereq = any(
                prereq in topic_lower or topic_lower in prereq
                for prereq in known_lower
            )
            if is_prereq and tg.content_needs.priority != "high":
                logger.info(f"Filtered prerequisite-overlap topic: '{tg.name}'")
                continue
            filtered.append(tg)
        if len(filtered) >= 3:
            topic_tree.topic_groups = filtered

    logger.info(
        f"Decompose complete: effort_tier={topic_tree.effort_tier}, "
        f"{num_topics} topics, avg {avg_queries:.1f} queries/topic"
    )

    return topic_tree
