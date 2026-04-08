"""Animation Agent v2 pipeline — generates visual assets for lesson storyboards."""

import asyncio
import logging
import time

from app.engine.claude_engine import ClaudeEngine
from app.agents.animation_v2.generator import generate_frame_visual, route_frame
from app.services.supabase import get_supabase

logger = logging.getLogger(__name__)

BATCH_SIZE = 3
MAX_RETRIES = 2
RETRY_DELAY = 30  # seconds between retry rounds


def _upload_result(sb, goal_id, user_id, lesson_id, r: dict):
    """Upload completed HTML to Supabase Storage and save to lesson_animations."""
    frame_id = r["frame_id"]
    storage_path = f"visuals/{goal_id}/{lesson_id}/{frame_id}.html"
    html_bytes = r["html"].encode("utf-8")

    sb.storage.from_("animations").upload(
        storage_path, html_bytes,
        file_options={"content-type": "text/html", "upsert": "true"},
    )

    public_url = sb.storage.from_("animations").get_public_url(storage_path)
    r["url"] = public_url

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

    return public_url


async def generate_lesson_visuals(
    goal_id: str,
    user_id: str,
    lesson_id: str,
) -> dict:
    """Generate all visual assets for one lesson's VisualFrames."""
    sb = get_supabase()
    engine = ClaudeEngine(model="sonnet")
    pipeline_start = time.time()

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

    # Inject goal_id/lesson_id into each frame for Manim upload path
    for f in frames:
        f["_goal_id"] = goal_id
        f["_lesson_id"] = lesson_id

    # Log routing decisions
    routing = {f.get("frame_id", "?"): route_frame(f) for f in frames}
    manim_count = sum(1 for r in routing.values() if r == "manim")
    browser_count = len(routing) - manim_count
    progress(f"Generating {len(frames)} frames ({browser_count} browser, {manim_count} manim)...", 5)
    if manim_count:
        manim_ids = [fid for fid, r in routing.items() if r == "manim"]
        logger.info(f"[AnimV2] Manim frames: {manim_ids}")

    # results_map: frame_id -> result dict
    results_map: dict[str, dict] = {}

    async def _run_batch(batch_frames: list[dict], label: str, is_retry: bool = False):
        """Run a batch of frames in parallel and collect results.

        On retry, passes previous error + code so Claude can fix instead of regenerate.
        """
        fids = [f.get("frame_id", "?") for f in batch_frames]
        progress(f"{label}: {'fixing' if is_retry else 'generating'} {', '.join(fids)}...")

        async def _gen(frame):
            fid = frame.get("frame_id", "?")
            prev = results_map.get(fid, {})
            if is_retry and prev.get("failed_code"):
                return await generate_frame_visual(
                    engine, frame, progress,
                    previous_error=prev.get("error", ""),
                    previous_code=prev.get("failed_code"),
                )
            return await generate_frame_visual(engine, frame, progress)

        batch_results = await asyncio.gather(
            *[_gen(f) for f in batch_frames],
            return_exceptions=True,
        )

        for frame, r in zip(batch_frames, batch_results):
            fid = frame.get("frame_id", "?")
            if isinstance(r, Exception):
                logger.error(f"[AnimV2] {fid} exception: {r}")
                results_map[fid] = {"frame_id": fid, "status": "failed", "error": str(r)}
            elif isinstance(r, dict):
                results_map[fid] = r
                if r.get("status") == "completed" and r.get("html"):
                    try:
                        url = _upload_result(sb, goal_id, user_id, lesson_id, r)
                        progress(f"[{fid}] Uploaded to storage")
                    except Exception as e:
                        logger.error(f"[AnimV2] Upload failed for {fid}: {e}")
                        r["upload_error"] = str(e)

    # --- Pass 1: generate all frames in batches ---
    for i in range(0, len(frames), BATCH_SIZE):
        batch = frames[i:i + BATCH_SIZE]
        batch_num = i // BATCH_SIZE + 1
        total_batches = (len(frames) + BATCH_SIZE - 1) // BATCH_SIZE
        pct = 5 + int(70 * i / len(frames))
        progress(f"Batch {batch_num}/{total_batches}", pct)

        await _run_batch(batch, f"Batch {batch_num}/{total_batches}")

        done = sum(1 for r in results_map.values() if r.get("status") == "completed")
        fail = sum(1 for r in results_map.values() if r.get("status") == "failed")
        progress(f"{done} completed, {fail} failed, {len(frames) - len(results_map)} remaining", pct)

    # --- Pass 2+: auto-retry failed frames ---
    for retry_round in range(1, MAX_RETRIES + 1):
        failed_frames = [f for f in frames
                         if results_map.get(f.get("frame_id", ""), {}).get("status") == "failed"]
        if not failed_frames:
            break

        fids = [f.get("frame_id") for f in failed_frames]
        logger.info(f"[AnimV2] Retry round {retry_round}/{MAX_RETRIES}: {len(failed_frames)} frames ({fids})")
        progress(f"Retry {retry_round}: {len(failed_frames)} failed frames...", 80 + retry_round * 5)

        # Brief pause before retry to let rate limits clear
        await asyncio.sleep(RETRY_DELAY)

        # Retry in smaller batches of 2 to reduce rate limit pressure
        retry_batch_size = 2
        for i in range(0, len(failed_frames), retry_batch_size):
            batch = failed_frames[i:i + retry_batch_size]
            await _run_batch(batch, f"Retry {retry_round}", is_retry=True)

    # --- Final summary ---
    results = [results_map.get(f.get("frame_id", ""), {"status": "missing"}) for f in frames]
    completed = sum(1 for r in results if r.get("status") == "completed")
    failed = sum(1 for r in results if r.get("status") == "failed")
    total_size = sum(r.get("html_size", 0) for r in results if r.get("status") == "completed")
    elapsed = time.time() - pipeline_start

    progress(
        f"Done: {completed}/{len(frames)} visuals ({total_size // 1024}KB, {elapsed/60:.0f} min)"
        f"{f' — {failed} failed after {MAX_RETRIES} retries' if failed else ''}",
        100,
    )

    manim_completed = sum(1 for r in results if r.get("status") == "completed" and r.get("renderer") == "manim")
    browser_completed = completed - manim_completed
    logger.info(f"[AnimV2] Lesson {lesson_id}: {completed}/{len(frames)} completed "
                f"({browser_completed} browser, {manim_completed} manim), "
                f"{failed} failed, {elapsed:.0f}s total")

    return {
        "lesson_id": lesson_id,
        "total_frames": len(frames),
        "completed": completed,
        "failed": failed,
        "manim_completed": manim_completed,
        "browser_completed": browser_completed,
        "pipeline_seconds": round(elapsed, 1),
        "results": results,
    }
