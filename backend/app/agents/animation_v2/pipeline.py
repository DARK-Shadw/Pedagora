"""Animation Agent v2 pipeline — generates visual assets for lesson storyboards."""

import asyncio
import json
import logging
from datetime import datetime, timezone

from app.engine.claude_engine import ClaudeEngine
from app.agents.animation_v2.generator import generate_frame_visual
from app.services.supabase import get_supabase

logger = logging.getLogger(__name__)


async def generate_lesson_visuals(
    goal_id: str,
    user_id: str,
    lesson_id: str,
) -> dict:
    """Generate all visual assets for one lesson's VisualFrames."""
    sb = get_supabase()
    engine = ClaudeEngine(model="sonnet")

    def progress(msg: str, pct: int | None = None):
        update = {"current_task": msg}
        if pct is not None:
            update["progress_percentage"] = pct
        try:
            sb.table("agent_tasks").update(update).eq(
                "goal_id", goal_id).eq("agent_type", "visualization").execute()
        except Exception:
            pass
        logger.info(f"[AnimV2] {msg}")

    # Load lesson frames from course plan
    cp = sb.table("course_plans").select("lesson_plans").eq("goal_id", goal_id).single().execute()
    if not cp.data:
        raise RuntimeError("No course plan found")

    lesson = cp.data["lesson_plans"].get(lesson_id, {})
    frames = lesson.get("frames", [])
    if not frames:
        raise RuntimeError(f"No frames found for lesson {lesson_id}")

    progress(f"Generating visuals for {len(frames)} frames...", 5)

    # Generate in batches of 3 (parallel)
    results = []
    batch_size = 3
    for i in range(0, len(frames), batch_size):
        batch = frames[i:i + batch_size]
        batch_num = i // batch_size + 1
        total_batches = (len(frames) + batch_size - 1) // batch_size
        pct = 5 + int(85 * i / len(frames))

        progress(f"Batch {batch_num}/{total_batches}: generating {len(batch)} visuals...", pct)

        batch_results = await asyncio.gather(
            *[generate_frame_visual(engine, f, progress) for f in batch],
            return_exceptions=True,
        )

        for r in batch_results:
            if isinstance(r, Exception):
                logger.error(f"[AnimV2] Frame exception: {r}")
                results.append({"status": "failed", "error": str(r)})
            elif isinstance(r, dict):
                results.append(r)

                # Upload HTML to Supabase Storage if completed
                if r.get("status") == "completed" and r.get("html"):
                    try:
                        frame_id = r["frame_id"]
                        storage_path = f"visuals/{goal_id}/{lesson_id}/{frame_id}.html"
                        html_bytes = r["html"].encode("utf-8")

                        # Upload to storage
                        sb.storage.from_("animations").upload(
                            storage_path, html_bytes,
                            file_options={"content-type": "text/html", "upsert": "true"},
                        )

                        # Get public URL
                        public_url = sb.storage.from_("animations").get_public_url(storage_path)
                        r["url"] = public_url

                        # Save to lesson_animations table
                        sb.table("lesson_animations").upsert({
                            "goal_id": goal_id,
                            "user_id": user_id,
                            "lesson_id": lesson_id,
                            "animation_id": frame_id,
                            "animation_type": r.get("visual_type", "animation"),
                            "status": "completed",
                            "output_url": public_url,
                            "render_time_seconds": r.get("elapsed_seconds", 0),
                        }, on_conflict="goal_id,lesson_id,animation_id").execute()

                        progress(f"[{frame_id}] Uploaded to storage")
                    except Exception as e:
                        logger.error(f"[AnimV2] Upload failed for {r.get('frame_id')}: {e}")
                        r["upload_error"] = str(e)

        # Save progress incrementally
        completed = sum(1 for r in results if r.get("status") == "completed")
        failed = sum(1 for r in results if r.get("status") == "failed")
        progress(f"{completed} completed, {failed} failed, {len(frames) - len(results)} remaining", pct)

    # Final summary
    completed = sum(1 for r in results if r.get("status") == "completed")
    failed = sum(1 for r in results if r.get("status") == "failed")
    total_size = sum(r.get("html_size", 0) for r in results if r.get("status") == "completed")

    progress(f"Done: {completed}/{len(frames)} visuals generated ({total_size // 1024}KB total)", 100)

    logger.info(f"[AnimV2] Lesson {lesson_id}: {completed} completed, {failed} failed")

    return {
        "lesson_id": lesson_id,
        "total_frames": len(frames),
        "completed": completed,
        "failed": failed,
        "results": results,
    }
