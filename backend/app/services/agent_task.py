from datetime import datetime, timezone

from app.services.supabase import get_supabase


async def fetch_onboarding_data(goal_id: str, user_id: str) -> dict:
    """Fetch all onboarding data needed by the research agent."""
    sb = get_supabase()

    goal = (
        sb.table("learning_goals")
        .select("*")
        .eq("id", goal_id)
        .eq("user_id", user_id)
        .single()
        .execute()
    )

    preferences = (
        sb.table("user_preferences")
        .select("*")
        .eq("user_id", user_id)
        .single()
        .execute()
    )

    profile = (
        sb.table("profiles")
        .select("education_level")
        .eq("id", user_id)
        .single()
        .execute()
    )

    prerequisites = (
        sb.table("prerequisites")
        .select("*")
        .eq("goal_id", goal_id)
        .eq("user_id", user_id)
        .execute()
    )

    assessments = (
        sb.table("skill_assessments")
        .select("*")
        .eq("goal_id", goal_id)
        .eq("user_id", user_id)
        .execute()
    )

    return {
        "goal": goal.data,
        "preferences": preferences.data,
        "profile": profile.data,
        "prerequisites": prerequisites.data or [],
        "assessments": assessments.data or [],
    }


async def get_agent_task(goal_id: str, agent_type: str) -> dict | None:
    """Get the agent task row for a goal + agent type."""
    sb = get_supabase()
    result = (
        sb.table("agent_tasks")
        .select("*")
        .eq("goal_id", goal_id)
        .eq("agent_type", agent_type)
        .single()
        .execute()
    )
    return result.data


async def update_agent_task(
    goal_id: str,
    agent_type: str,
    *,
    status: str | None = None,
    progress: float | None = None,
    current_task: str | None = None,
    focus: str | None = None,
    log_message: str | None = None,
    log_level: str = "info",
    error_message: str | None = None,
) -> None:
    """Update agent_tasks row — triggers Supabase Realtime for frontend."""
    sb = get_supabase()

    update_data: dict = {}

    if status is not None:
        update_data["status"] = status
        if status == "active":
            update_data["started_at"] = datetime.now(timezone.utc).isoformat()
        elif status in ("completed", "failed"):
            update_data["completed_at"] = datetime.now(timezone.utc).isoformat()

    if progress is not None:
        update_data["progress_percentage"] = progress

    if current_task is not None:
        update_data["current_task"] = current_task

    if focus is not None:
        update_data["focus"] = focus

    if error_message is not None:
        update_data["error_message"] = error_message

    # Append to logs array if a log message is provided
    if log_message is not None:
        existing = (
            sb.table("agent_tasks")
            .select("logs")
            .eq("goal_id", goal_id)
            .eq("agent_type", agent_type)
            .single()
            .execute()
        )
        logs = existing.data.get("logs", []) if existing.data else []
        logs.append(
            {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "agent": "research",
                "message": log_message,
                "level": log_level,
            }
        )
        update_data["logs"] = logs

    if update_data:
        sb.table("agent_tasks").update(update_data).eq("goal_id", goal_id).eq(
            "agent_type", agent_type
        ).execute()


async def save_research_sources(
    goal_id: str, user_id: str, sources: list[dict]
) -> None:
    """Save research sources to the database."""
    if not sources:
        return

    sb = get_supabase()

    rows = []
    for s in sources:
        # Build extracted_content JSONB from the nested model
        extracted = s.get("extracted_content") or {}
        formulas = extracted.get("formulas", []) if extracted else []
        code_snippets = extracted.get("code_snippets", []) if extracted else []
        numerical_examples = extracted.get("numerical_examples", []) if extracted else []
        difficulty_level = extracted.get("difficulty_level") if extracted else None

        rows.append(
            {
                "goal_id": goal_id,
                "user_id": user_id,
                "topic_group": s.get("topic_group", "general"),
                "source_type": s.get("source_type", "article"),
                "title": s.get("title", "Untitled"),
                "url": s.get("url"),
                "author": s.get("author"),
                "summary": s.get("summary"),
                "key_concepts": s.get("key_concepts", []),
                "relevance_score": s.get("relevance_score", 0),
                "credibility_score": s.get("credibility_score", 0),
                "content_extract": s.get("content_extract"),
                "metadata": s.get("metadata", {}),
                # v2 columns
                "extracted_content": extracted,
                "formulas": formulas,
                "code_snippets": code_snippets,
                "numerical_examples": numerical_examples,
                "difficulty_level": difficulty_level,
            }
        )

    sb.table("research_sources").insert(rows).execute()


async def save_research_results(
    goal_id: str, user_id: str, topic_tree: dict, synthesis: dict, source_count: int
) -> None:
    """Save or update the full research result for a goal."""
    sb = get_supabase()

    sb.table("research_results").upsert(
        {
            "goal_id": goal_id,
            "user_id": user_id,
            "topic_tree": topic_tree,
            "synthesis": synthesis,
            "source_count": source_count,
            # v2 columns
            "teaching_notes": synthesis.get("teaching_notes", {}),
            "demo_codebases": synthesis.get("demo_codebases", []),
            "coding_exercises": synthesis.get("coding_exercises", []),
            "cross_topic_formulas": synthesis.get("cross_topic_formulas", []),
            "version": 2,
        },
        on_conflict="goal_id",
    ).execute()


async def cleanup_previous_research(goal_id: str) -> None:
    """Remove previous research data for retry scenarios."""
    sb = get_supabase()
    sb.table("research_sources").delete().eq("goal_id", goal_id).execute()
    sb.table("research_results").delete().eq("goal_id", goal_id).execute()
