from datetime import datetime, timezone

from app.services.supabase import get_supabase


async def fetch_onboarding_data(goal_id: str, user_id: str) -> dict:
    """Fetch all onboarding data needed by agents."""
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
    metadata: dict | None = None,
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

    if metadata is not None:
        update_data["metadata"] = metadata

    if update_data:
        sb.table("agent_tasks").update(update_data).eq("goal_id", goal_id).eq(
            "agent_type", agent_type
        ).execute()

    if log_message is not None:
        sb.rpc(
            "append_agent_task_log",
            {
                "p_goal_id": goal_id,
                "p_agent_type": agent_type,
                "p_log_entry": {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "agent": agent_type,
                    "message": log_message,
                    "level": log_level,
                },
            },
        ).execute()


# ─── Course Plan helpers (used by episode planner + teacher) ───


async def fetch_course_plan(goal_id: str) -> dict | None:
    """Fetch the course plan for a goal."""
    sb = get_supabase()
    result = (
        sb.table("course_plans")
        .select("*")
        .eq("goal_id", goal_id)
        .single()
        .execute()
    )
    return result.data


async def save_course_plan(
    goal_id: str,
    user_id: str,
    course_structure: dict,
    lesson_plans: dict,
    student_resource_map: dict,
    total_lessons: int,
    total_modules: int,
    total_estimated_minutes: int,
) -> None:
    """Save or update the course plan for a goal."""
    sb = get_supabase()
    sb.table("course_plans").upsert(
        {
            "goal_id": goal_id,
            "user_id": user_id,
            "course_structure": course_structure,
            "lesson_plans": lesson_plans,
            "student_resource_map": student_resource_map,
            "total_lessons": total_lessons,
            "total_modules": total_modules,
            "total_estimated_minutes": total_estimated_minutes,
            "version": 1,
        },
        on_conflict="goal_id",
    ).execute()


# ─── Animation helpers ───


async def save_animation_result(
    goal_id: str,
    user_id: str,
    lesson_id: str,
    animation_id: str,
    animation_type: str,
    status: str,
    manim_code: str,
    output_path: str,
    output_url: str,
    error_log: str | None,
    render_time: float,
) -> None:
    """Save or update an animation result."""
    sb = get_supabase()
    sb.table("lesson_animations").upsert(
        {
            "goal_id": goal_id,
            "user_id": user_id,
            "lesson_id": lesson_id,
            "animation_id": animation_id,
            "animation_type": animation_type,
            "status": status,
            "manim_code": manim_code,
            "output_path": output_path,
            "output_url": output_url,
            "error_log": error_log,
            "render_time_seconds": render_time,
        },
        on_conflict="goal_id,lesson_id,animation_id",
    ).execute()


async def get_lesson_animations(goal_id: str, lesson_id: str) -> list[dict]:
    """Get all animation results for a lesson."""
    sb = get_supabase()
    result = (
        sb.table("lesson_animations")
        .select("*")
        .eq("goal_id", goal_id)
        .eq("lesson_id", lesson_id)
        .execute()
    )
    return result.data or []
