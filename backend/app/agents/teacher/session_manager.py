"""Session management for teaching sessions.

Handles creating, loading, saving, and resuming teaching sessions,
plus shareable lesson links.

On session creation, kicks off a background prefetch task that:
  1. Loads Piper TTS (warmup)
  2. Reads the lesson's animation step labels from local HTML files
  3. Generates per-step LLM speeches
  4. Synthesizes audio for every frame, storing in the session's audio cache

This makes the user's lesson-start wait time bounded by frame 0's prefetch
(~2-3s) instead of the previous ~24s opening synth.
"""

import asyncio
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
    """Create a new teaching session and kick off background audio prefetch."""
    sb = get_supabase()
    result = sb.table("teaching_sessions").insert({
        "goal_id": goal_id,
        "lesson_id": lesson_id,
        "user_id": user_id,
        "status": "active",
        "dialogue_state": DialogueState().to_dict(),
        "student_scores": {},
    }).execute()
    session = result.data[0]

    # Kick off audio prefetch in background — does not block session creation.
    # If the user opens the classroom slowly, frames are already cached by then.
    asyncio.create_task(_prefetch_session_audio(
        session_id=session["id"],
        goal_id=goal_id,
        lesson_id=lesson_id,
        user_id=user_id,
    ))

    return session


async def _prefetch_session_audio(
    session_id: str,
    goal_id: str,
    lesson_id: str,
    user_id: str,
) -> None:
    """Background task: warmup Piper + generate audio for all frames."""
    try:
        from app.services.tts import warmup
        from app.services.audio_cache import get_or_create_cache
        from app.services.agent_task import fetch_course_plan, fetch_onboarding_data
        from app.agents.teacher.speech_gen import generate_step_speeches
        from app.routers.teacher import extract_animation_step_specs

        # 1. Load Piper voice (one-time per process)
        await warmup()

        # 2. Load course plan + lesson + student preferences
        course_plan = await fetch_course_plan(goal_id)
        if not course_plan:
            logger.warning(f"[Prefetch] {session_id} — no course plan, skipping")
            return

        lesson_plan = course_plan.get("lesson_plans", {}).get(lesson_id, {})
        frames = lesson_plan.get("frames", [])
        if not frames:
            logger.warning(f"[Prefetch] {session_id} — no frames in lesson {lesson_id}")
            return

        # Best-effort: load student name + teaching style
        student_name = ""
        teaching_style = "lecture"
        try:
            onboarding = await fetch_onboarding_data(goal_id, user_id)
            student_name = (onboarding.get("profile", {}) or {}).get("full_name", "")
            teaching_style = (onboarding.get("preferences", {}) or {}).get(
                "teaching_style", "lecture"
            )
        except Exception:
            pass

        cache = await get_or_create_cache(session_id)

        # 3. Sequential prefetch — Piper is fast (~1-2s per frame on CPU)
        # Sequential preserves order so frame 0 is ready first.
        logger.info(f"[Prefetch] {session_id} starting for {len(frames)} frames")
        for frame in frames:
            frame_id = frame.get("frame_id", "")
            if not frame_id:
                continue

            # Extract animation step labels from local HTML
            step_specs = await extract_animation_step_specs(
                goal_id, lesson_id, frame_id
            )
            if not step_specs:
                # Single-step fallback for animations with no labels
                step_specs = [{"label": "main", "anim_time": 0.0}]

            # Generate per-step speech text via LLM
            try:
                speeches = await generate_step_speeches(
                    frame=frame,
                    step_labels=[s["label"] for s in step_specs],
                    student_name=student_name,
                    teaching_style=teaching_style,
                )
            except Exception as e:
                logger.error(f"[Prefetch] {frame_id} speech gen failed: {e}")
                speeches = [
                    f"Now look at the {s['label'].replace('-', ' ')}."
                    for s in step_specs
                ]

            # Combine spec + text and prefetch audio
            combined_specs = [
                {**spec, "text": speeches[i] if i < len(speeches) else ""}
                for i, spec in enumerate(step_specs)
            ]
            await cache.prefetch(frame_id, combined_specs)

        logger.info(f"[Prefetch] {session_id} finished — {len(frames)} frames cached")
    except asyncio.CancelledError:
        logger.info(f"[Prefetch] {session_id} cancelled")
    except Exception as e:
        logger.error(f"[Prefetch] {session_id} failed: {e}", exc_info=True)


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
    """Mark a session as paused (student disconnected). Keeps cache in memory
    so a quick reconnect can resume without re-prefetching."""
    sb = get_supabase()
    sb.table("teaching_sessions").update({
        "status": "paused",
    }).eq("id", session_id).execute()


async def complete_session(
    session_id: str,
    summary: dict,
) -> None:
    """Mark a session as completed with summary. Discards the audio cache."""
    from datetime import datetime, timezone
    from app.services.audio_cache import discard_cache
    sb = get_supabase()
    sb.table("teaching_sessions").update({
        "status": "completed",
        "session_summary": summary,
        "completed_at": datetime.now(timezone.utc).isoformat(),
    }).eq("id", session_id).execute()
    await discard_cache(session_id)


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
