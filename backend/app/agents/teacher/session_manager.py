"""Session management for teaching sessions.

Handles creating, loading, saving, and resuming teaching sessions,
plus shareable lesson links.
"""

import logging
import secrets

from app.agents.teacher.dialogue_state import DialogueState
from app.services.supabase import get_supabase

logger = logging.getLogger(__name__)


async def create_session(
    goal_id: str,
    lesson_id: str,
    user_id: str,
) -> dict:
    """Create a new teaching session. Returns the session row."""
    sb = get_supabase()
    result = sb.table("teaching_sessions").insert({
        "goal_id": goal_id,
        "lesson_id": lesson_id,
        "user_id": user_id,
        "status": "active",
        "dialogue_state": DialogueState().to_dict(),
        "student_scores": {},
    }).execute()
    return result.data[0]


async def load_session(session_id: str) -> dict | None:
    """Load a teaching session by ID."""
    sb = get_supabase()
    result = sb.table("teaching_sessions").select("*").eq("id", session_id).execute()
    return result.data[0] if result.data else None


async def find_active_session(
    goal_id: str,
    lesson_id: str,
    user_id: str,
) -> dict | None:
    """Find an existing active/paused session for this user + lesson."""
    sb = get_supabase()
    result = (
        sb.table("teaching_sessions")
        .select("*")
        .eq("goal_id", goal_id)
        .eq("lesson_id", lesson_id)
        .eq("user_id", user_id)
        .in_("status", ["active", "paused"])
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    return result.data[0] if result.data else None


async def save_session_state(
    session_id: str,
    dialogue_state: DialogueState,
) -> None:
    """Save the current dialogue state to DB."""
    sb = get_supabase()
    sb.table("teaching_sessions").update({
        "current_segment_id": dialogue_state.current_segment_id,
        "dialogue_state": dialogue_state.to_dict(),
        "student_scores": dialogue_state.student_scores,
        "last_active_at": dialogue_state.last_active_at,
    }).eq("id", session_id).execute()


async def pause_session(session_id: str) -> None:
    """Mark a session as paused (student disconnected)."""
    sb = get_supabase()
    sb.table("teaching_sessions").update({
        "status": "paused",
    }).eq("id", session_id).execute()


async def complete_session(
    session_id: str,
    summary: dict,
) -> None:
    """Mark a session as completed with summary."""
    from datetime import datetime, timezone
    sb = get_supabase()
    sb.table("teaching_sessions").update({
        "status": "completed",
        "session_summary": summary,
        "completed_at": datetime.now(timezone.utc).isoformat(),
    }).eq("id", session_id).execute()


# ─── Share Links ───


async def create_share_link(
    goal_id: str,
    lesson_id: str,
    user_id: str,
) -> str:
    """Create a shareable lesson link. Returns the share_code."""
    sb = get_supabase()
    share_code = secrets.token_urlsafe(6)  # ~8 chars, URL-safe

    sb.table("lesson_links").insert({
        "goal_id": goal_id,
        "lesson_id": lesson_id,
        "share_code": share_code,
        "created_by": user_id,
    }).execute()

    return share_code


async def resolve_share_link(share_code: str) -> dict | None:
    """Resolve a share code to goal_id + lesson_id."""
    sb = get_supabase()
    result = (
        sb.table("lesson_links")
        .select("goal_id, lesson_id, is_active")
        .eq("share_code", share_code)
        .eq("is_active", True)
        .execute()
    )
    return result.data[0] if result.data else None
