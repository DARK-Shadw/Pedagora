"""Animation Agent v2 pipeline — generates visual assets for lesson storyboards.

PIPELINE STAGE 3 (see docs/architecture-flow.svg)

Flow per lesson:
  1. Load frames from course_plans (output of Episode Planner)
  2. Route each frame: browser (GSAP/HTML) or Manim (Python → MP4)
  3. Generate code via multi-provider LLM chain (Gemini → NVIDIA → Groq)
  4. Validate in headless Playwright browser (labels, errors, screenshots)
  5. On failure: feed error back into fix prompt, retry up to 2x
  6. Upload completed HTML to Supabase Storage (public CDN URLs)
  7. Save results to lesson_animations table

Concurrency: frames processed in parallel (semaphore-bounded).
Resume support: skips frames already completed from a previous run.
"""

import asyncio
import datetime as _dt
import logging
import re
import time

from app.agents.animation_v2.gemini_client import GeminiClient, MODEL_ID as GEMINI_MODEL_ID
from app.agents.animation_v2.groq_client import GroqCodeClient
from app.agents.animation_v2.narration import generate_frame_narration
from app.agents.animation_v2.nvidia_client import NvidiaClient
from app.agents.animation_v2.generator import generate_frame_visual, route_frame
from app.config import get_settings
from app.services.supabase import get_supabase

logger = logging.getLogger(__name__)

BATCH_SIZE = 3
MAX_RETRIES = 2
RETRY_DELAY = 30  # seconds between retry rounds


async def regenerate_single_frame(
    goal_id: str,
    user_id: str,
    lesson_id: str,
    frame_id: str,
) -> dict:
    """Regenerate a single animation frame.

    Deletes the existing lesson_animations row (if any), re-runs the full
    generate → validate → upload cycle, and upserts the result. The frame's
    storyboard (visual_spec, steps, etc.) comes from the course plan — this
    function does NOT modify the storyboard.
    """
    sb = get_supabase()
    settings = get_settings()
    keys = settings.get_gemini_api_keys()
    if keys:
        gemini = GeminiClient(
            keys,
            paid_key=settings.gemini_paid_api_key or None,
            paid_model=settings.gemini_paid_model or None,
        )
    else:
        try:
            gemini = NvidiaClient()
        except (ValueError, Exception):
            raise RuntimeError("No animation API keys configured (Gemini or NVIDIA)")

    # Load the frame from the course plan
    cp = sb.table("course_plans").select("lesson_plans").eq("goal_id", goal_id).single().execute()
    if not cp.data:
        raise RuntimeError("No course plan found")

    lesson = cp.data["lesson_plans"].get(lesson_id, {})
    frames = lesson.get("frames", [])
    frame = next((f for f in frames if f.get("frame_id") == frame_id), None)
    if not frame:
        raise RuntimeError(f"Frame {frame_id} not found in lesson {lesson_id}")

    frame["_goal_id"] = goal_id
    frame["_lesson_id"] = lesson_id

    # Mark existing row as pending so the UI reflects regeneration in progress
    try:
        sb.table("lesson_animations").update(
            {"status": "pending", "error_log": None}
        ).eq("goal_id", goal_id).eq("lesson_id", lesson_id).eq(
            "animation_id", frame_id
        ).execute()
    except Exception:
        pass  # Row may not exist yet

    def progress(msg: str, pct: int | None = None):
        logger.info(f"[AnimV2-regen] {msg}")

    logger.info(
        f"[AnimV2-regen] Regenerating {frame_id} in {lesson_id} "
        f"(route={route_frame(frame)})"
    )

    result = await generate_frame_visual(gemini, frame, progress)

    if result.get("status") == "completed" and result.get("html"):
        _upload_result(sb, goal_id, user_id, lesson_id, result)
        logger.info(
            f"[AnimV2-regen] {frame_id} regenerated OK: "
            f"{result.get('renderer')} {result.get('html_size', 0)} chars"
        )
    else:
        error = result.get("error", "unknown")
        logger.error(f"[AnimV2-regen] {frame_id} regeneration FAILED: {error}")
        # Record failure in DB
        try:
            sb.table("lesson_animations").upsert({
                "goal_id": goal_id,
                "user_id": user_id,
                "lesson_id": lesson_id,
                "animation_id": frame_id,
                "animation_type": frame.get("visual_type", "animation"),
                "status": "failed",
                "error_log": error[:2000],
            }, on_conflict="goal_id,lesson_id,animation_id").execute()
        except Exception as e:
            logger.warning(f"[AnimV2-regen] Failed to record error: {e}")

    return result


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


def _save_narrations_to_course_plan(
    sb, goal_id: str, lesson_id: str,
    frames: list[dict], results_map: dict[str, dict],
) -> int:
    """Write generated narrations back to course_plans.lesson_plans.

    Updates each frame's steps[].narration_spoken with the pipeline-generated
    narration so the Teacher Agent picks it up directly (no runtime Groq call).
    Runs once after all frames are done — single DB read + write, no concurrency risk.

    Returns the number of frames that had narration saved.
    """
    narration_map: dict[str, list[str]] = {}
    for fid, result in results_map.items():
        texts = result.get("narration_texts")
        if texts and isinstance(texts, list) and result.get("status") == "completed":
            narration_map[fid] = texts

    if not narration_map:
        return 0

    try:
        cp = sb.table("course_plans").select("lesson_plans").eq(
            "goal_id", goal_id,
        ).single().execute()
        if not cp.data:
            return 0

        lesson_plans = cp.data["lesson_plans"]
        lesson = lesson_plans.get(lesson_id, {})
        db_frames = lesson.get("frames", [])

        updated = 0
        for frame in db_frames:
            fid = frame.get("frame_id", "")
            narrations = narration_map.get(fid)
            if not narrations:
                continue
            steps = frame.get("steps", [])
            if len(narrations) != len(steps):
                logger.warning(
                    f"[AnimV2] narration count mismatch for {fid}: "
                    f"{len(narrations)} narrations vs {len(steps)} steps"
                )
                continue
            for step, text in zip(steps, narrations):
                step["narration_spoken"] = text
            updated += 1

        if updated:
            lesson["frames"] = db_frames
            lesson_plans[lesson_id] = lesson
            sb.table("course_plans").update(
                {"lesson_plans": lesson_plans},
            ).eq("goal_id", goal_id).execute()
            logger.info(
                f"[AnimV2] Saved narrations for {updated}/{len(db_frames)} "
                f"frames to course plan"
            )

        return updated
    except Exception as e:
        logger.error(f"[AnimV2] Failed to save narrations to course plan: {e}")
        return 0


async def generate_lesson_visuals(
    goal_id: str,
    user_id: str,
    lesson_id: str,
) -> dict:
    """Generate all visual assets for one lesson's VisualFrames."""
    sb = get_supabase()
    settings = get_settings()

    # Provider chain: Gemini 3 Flash → NVIDIA DeepSeek → Groq
    keys = settings.get_gemini_api_keys()
    if keys:
        gemini = GeminiClient(
            keys,
            paid_key=settings.gemini_paid_api_key or None,
            paid_model=settings.gemini_paid_model or None,
        )
        provider_name = f"Gemini {GEMINI_MODEL_ID}"
        if settings.gemini_paid_api_key:
            provider_name += f" + paid fallback ({settings.gemini_paid_model})"
    else:
        try:
            gemini = NvidiaClient()
            provider_name = "NVIDIA DeepSeek V4 Flash"
        except (ValueError, Exception):
            try:
                gemini = GroqCodeClient()
                provider_name = "Groq openai/gpt-oss-120b"
            except (ValueError, Exception):
                raise RuntimeError(
                    "No animation API keys configured — set GEMINI_API_KEYS, "
                    "NVIDIA_API_KEY, or GROQ_API_KEY in backend/.env"
                )
    pipeline_start = time.time()

    def _log(msg: str, level: str = "info"):
        """Milestone log — goes to append_agent_task_log RPC so it shows in
        the System Execution Logs UI panel. Keep calls to meaningful events
        (lesson start, per-frame ok/fail, batch summary, retry round, done)."""
        try:
            sb.rpc(
                "append_agent_task_log",
                {
                    "p_goal_id": goal_id,
                    "p_agent_type": "visualization",
                    "p_log_entry": {
                        "timestamp": _dt.datetime.now(_dt.timezone.utc).isoformat(),
                        "agent": "visualization",
                        "message": msg,
                        "level": level,
                    },
                },
            ).execute()
        except Exception:
            pass
        logger.info(f"[AnimV2] {msg}")

    # Progress messages containing any of these substrings are promoted
    # from the current_task column (overwritten by sibling frames) to
    # a real System Execution Logs entry. Covers long Manim render
    # checkpoints, upload confirmations, and Gemini code-gen milestones.
    _PROGRESS_MILESTONES = (
        "still rendering",
        "Rendered",
        "MP4 uploaded",
        "Code generated",
    )

    def progress(msg: str, pct: int | None = None):
        """Lightweight UI status update — updates current_task column, and
        for milestone messages also posts to _log so long-running frames
        stay visible in System Execution Logs."""
        update = {"current_task": msg}
        if pct is not None:
            update["progress_percentage"] = pct
        try:
            sb.table("agent_tasks").update(update).eq(
                "goal_id", goal_id).eq("agent_type", "visualization").execute()
        except Exception:
            pass
        logger.info(f"[AnimV2] {msg}")
        if any(s in msg for s in _PROGRESS_MILESTONES):
            _log(msg)

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

    # --- Resume support: skip frames already completed in a previous run ---
    # Query lesson_animations for rows already marked completed for this lesson
    # so we don't re-burn Gemini calls on work we already have in storage.
    already_done: dict[str, dict] = {}
    try:
        existing = (
            sb.table("lesson_animations")
            .select("animation_id,output_url,animation_type,render_time_seconds")
            .eq("goal_id", goal_id)
            .eq("lesson_id", lesson_id)
            .eq("status", "completed")
            .execute()
        )
        for row in (existing.data or []):
            fid = row.get("animation_id")
            if fid and row.get("output_url"):
                already_done[fid] = row
    except Exception as e:
        logger.warning(f"[AnimV2] Could not query existing animations for resume: {e}")

    frames_to_process = [f for f in frames if f.get("frame_id") not in already_done]

    # results_map: frame_id -> result dict (pre-seeded with already-done frames)
    results_map: dict[str, dict] = {}
    for fid, row in already_done.items():
        results_map[fid] = {
            "frame_id": fid,
            "status": "completed",
            "renderer": "browser",  # unknown from DB; cosmetic only
            "visual_type": row.get("animation_type", "animation"),
            "url": row.get("output_url"),
            "elapsed_seconds": row.get("render_time_seconds") or 0,
            "resumed": True,
        }

    # Log routing decisions (only for frames we'll actually process this run)
    routing = {f.get("frame_id", "?"): route_frame(f) for f in frames_to_process}
    manim_count = sum(1 for r in routing.values() if r == "manim")
    browser_count = len(routing) - manim_count
    resume_suffix = f" (skipped {len(already_done)} already done)" if already_done else ""
    progress(
        f"Generating {len(frames_to_process)} frames "
        f"({browser_count} browser, {manim_count} manim){resume_suffix}...",
        5,
    )
    _log(
        f"[{lesson_id}] {provider_name} (pool: {gemini.pool_size}) · "
        f"animating {len(frames_to_process)} frames "
        f"({browser_count} browser, {manim_count} manim)"
        f"{resume_suffix}"
    )
    if manim_count:
        manim_ids = [fid for fid, r in routing.items() if r == "manim"]
        logger.info(f"[AnimV2] Manim frames: {manim_ids}")
    if already_done:
        logger.info(
            f"[AnimV2] Resume: {len(already_done)} frames already completed, "
            f"skipping: {sorted(already_done.keys())}"
        )

    async def _gen_one(frame: dict, is_retry: bool = False):
        """Generate one frame end-to-end and record the result in results_map.
        Reused by both the main pass and the retry rounds.
        """
        fid = frame.get("frame_id", "?")
        renderer_hint = route_frame(frame)
        prev = results_map.get(fid, {})
        _log(
            f"[{fid}] Starting {renderer_hint} generation"
            + (f" (retry: {str(prev.get('error', ''))[:80]})"
               if is_retry and prev.get("failed_code") else "")
        )
        try:
            if is_retry and prev.get("failed_code"):
                r = await generate_frame_visual(
                    gemini, frame, progress,
                    previous_error=prev.get("error", ""),
                    previous_code=prev.get("failed_code"),
                )
            else:
                r = await generate_frame_visual(gemini, frame, progress)
        except Exception as e:
            logger.error(
                f"[AnimV2] {fid} unhandled exception during generation",
                exc_info=True,
            )
            r = {"frame_id": fid, "status": "failed", "error": f"Exception: {e}"}

        if not isinstance(r, dict):
            r = {"frame_id": fid, "status": "failed",
                 "error": f"Bad return type: {type(r).__name__}"}

        results_map[fid] = r

        if r.get("status") == "completed":
            elapsed = r.get("elapsed_seconds", 0) or 0
            key_idx = r.get("key_index")
            key_part = f" (key#{key_idx})" if key_idx is not None else ""
            rtok = r.get("tokens_out")
            tok_part = f" [{rtok} tok]" if rtok else ""
            _log(
                f"[{fid}] {r.get('renderer', renderer_hint)} OK "
                f"in {elapsed:.0f}s{key_part}{tok_part}"
            )
            if r.get("html"):
                try:
                    _upload_result(sb, goal_id, user_id, lesson_id, r)
                    progress(f"[{fid}] Uploaded to storage")
                except Exception as e:
                    logger.error(
                        f"[AnimV2] {fid} upload failed: {e}", exc_info=True,
                    )
                    r["upload_error"] = str(e)
                    _log(f"[{fid}] upload failed: {str(e)[:160]}", "error")
        else:
            err = str(r.get("error", "unknown"))
            logger.error(f"[AnimV2] {fid} FAILED — full error:\n{err}")
            _log(f"[{fid}] FAILED: {err[:240]}", "error")
        return r

    # --- Pass 1: semaphore-bounded concurrent generation ---
    # NvidiaClient: 4 concurrent, GeminiClient: 3 concurrent, Groq: sequential
    concurrency = gemini.pool_size if hasattr(gemini, 'pool_size') else BATCH_SIZE
    if isinstance(gemini, GroqCodeClient):
        concurrency = 1
    work_total = max(1, len(frames_to_process))
    sem = asyncio.Semaphore(concurrency)
    completed_counter = 0

    async def _bounded_main(frame: dict):
        nonlocal completed_counter
        async with sem:
            await _gen_one(frame, is_retry=False)
        completed_counter += 1
        done = sum(1 for r in results_map.values() if r.get("status") == "completed")
        fail = sum(1 for r in results_map.values() if r.get("status") == "failed")
        remaining = len(frames_to_process) - completed_counter
        pct = 5 + int(70 * completed_counter / work_total)
        progress(
            f"{done} completed, {fail} failed, {remaining} remaining",
            pct,
        )

    if frames_to_process:
        _log(
            f"[{lesson_id}] Starting {len(frames_to_process)} frames "
            f"(concurrency={concurrency})"
        )
        await asyncio.gather(
            *[_bounded_main(f) for f in frames_to_process],
            return_exceptions=False,  # _gen_one handles its own exceptions
        )
        main_done = sum(
            1 for f in frames_to_process
            if results_map.get(f.get("frame_id", ""), {}).get("status") == "completed"
        )
        main_fail = len(frames_to_process) - main_done
        _log(
            f"[{lesson_id}] Main pass done: "
            f"{main_done} completed, {main_fail} failed"
        )

    # --- Pass 2+: auto-retry failed frames (also semaphore-bounded) ---
    for retry_round in range(1, MAX_RETRIES + 1):
        failed_frames = [f for f in frames_to_process
                         if results_map.get(f.get("frame_id", ""), {}).get("status") == "failed"]
        if not failed_frames:
            break

        fids = [f.get("frame_id") for f in failed_frames]
        logger.info(f"[AnimV2] Retry round {retry_round}/{MAX_RETRIES}: {len(failed_frames)} frames ({fids})")
        progress(f"Retry {retry_round}: {len(failed_frames)} failed frames...", 80 + retry_round * 5)
        _log(
            f"[{lesson_id}] Retry {retry_round}/{MAX_RETRIES}: "
            f"{len(failed_frames)} frames retrying",
            "warning",
        )

        # Brief pause before retry to let rate limits clear
        await asyncio.sleep(RETRY_DELAY)

        # Retry concurrency = 2 to reduce rate-limit pressure on Gemini.
        retry_sem = asyncio.Semaphore(2)

        async def _bounded_retry(frame: dict):
            async with retry_sem:
                await _gen_one(frame, is_retry=True)

        await asyncio.gather(
            *[_bounded_retry(f) for f in failed_frames],
            return_exceptions=False,
        )

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
    final_level = "info" if failed == 0 else ("error" if completed == 0 else "warning")
    _log(
        f"[{lesson_id}] Done: {completed}/{len(frames)} animated "
        f"({elapsed/60:.0f} min, {total_size // 1024}KB)"
        f"{f' — {failed} failed' if failed else ''}",
        final_level,
    )

    manim_completed = sum(1 for r in results if r.get("status") == "completed" and r.get("renderer") == "manim")
    browser_completed = completed - manim_completed
    logger.info(f"[AnimV2] Lesson {lesson_id}: {completed}/{len(frames)} completed "
                f"({browser_completed} browser, {manim_completed} manim), "
                f"{failed} failed, {elapsed:.0f}s total")

    # --- Save generated narrations back to course_plans ---
    narration_count = _save_narrations_to_course_plan(
        sb, goal_id, lesson_id, frames, results_map,
    )
    if narration_count:
        _log(f"[{lesson_id}] Saved narrations for {narration_count} frames to course plan")

    return {
        "lesson_id": lesson_id,
        "total_frames": len(frames),
        "completed": completed,
        "failed": failed,
        "manim_completed": manim_completed,
        "browser_completed": browser_completed,
        "narrations_saved": narration_count,
        "pipeline_seconds": round(elapsed, 1),
        "results": results,
    }


# ════════════════════════════════════════════════════════════
# Retry missing narrations — for frames that rendered OK but
# narration failed (rate-limit, timeout, etc.)
# ════════════════════════════════════════════════════════════

MIN_NARRATION_AVG_LEN = 50  # chars — below this, narration needs regeneration


async def _extract_gsap_labels_from_storage(
    sb, goal_id: str, lesson_id: str, frame_id: str,
) -> list[str]:
    """Fetch the generated HTML from Supabase Storage and extract GSAP labels."""
    import httpx

    storage_path = f"visuals/{goal_id}/{lesson_id}/{frame_id}.html"
    url = sb.storage.from_("animations").get_public_url(storage_path)

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(url)
            if resp.status_code != 200:
                return []
            html = resp.text
    except Exception:
        return []

    return re.findall(r"tl\.addLabel\(['\"]([^'\"]+)", html)


async def retry_missing_narrations(
    goal_id: str, lesson_id: str,
) -> dict:
    """Find completed frames with missing/short narrations and regenerate them.

    Scans the course plan for frames where the average narration_spoken length
    is below MIN_NARRATION_AVG_LEN (indicating Episode Planner stubs or failed
    pipeline narration). For each such frame, fetches validated GSAP labels from
    the stored HTML and re-runs narration generation with animation context.

    Uses the paid Gemini key (via max_key_rotations=1 fallback) to avoid
    competing with any active pipeline runs on the free key pool.
    """
    sb = get_supabase()
    settings = get_settings()

    cp = sb.table("course_plans").select("lesson_plans").eq(
        "goal_id", goal_id,
    ).single().execute()
    if not cp.data:
        return {"error": "Course plan not found"}

    lesson_plans = cp.data["lesson_plans"]
    lesson = lesson_plans.get(lesson_id)
    if not lesson:
        return {"error": f"Lesson '{lesson_id}' not found"}

    frames = lesson.get("frames", [])

    # Find completed animations (have a URL in lesson_animations)
    existing = (
        sb.table("lesson_animations")
        .select("animation_id,output_url")
        .eq("goal_id", goal_id)
        .eq("lesson_id", lesson_id)
        .eq("status", "completed")
        .execute()
    )
    completed_fids = {
        row["animation_id"]
        for row in (existing.data or [])
        if row.get("output_url")
    }

    # Find frames that need narration
    needs_narration: list[dict] = []
    for frame in frames:
        fid = frame.get("frame_id", "")
        if fid not in completed_fids:
            continue
        steps = frame.get("steps", [])
        if not steps:
            continue
        narrations = [s.get("narration_spoken", "") for s in steps]
        avg_len = sum(len(n) for n in narrations) / max(1, len(narrations))
        if avg_len < MIN_NARRATION_AVG_LEN:
            needs_narration.append(frame)

    if not needs_narration:
        return {
            "lesson_id": lesson_id,
            "frames_checked": len(frames),
            "frames_needing_narration": 0,
            "message": "All frames have adequate narrations",
        }

    logger.info(
        f"[NarrationRetry] {lesson_id}: {len(needs_narration)} frames need narration: "
        f"{[f.get('frame_id') for f in needs_narration]}"
    )

    # Init Gemini client — paid key will handle it via max_key_rotations=1
    gemini = GeminiClient(
        settings.get_gemini_api_keys(),
        paid_key=settings.gemini_paid_api_key or None,
        paid_model=settings.gemini_paid_model or None,
    )

    updated_count = 0
    results: list[dict] = []

    for frame in needs_narration:
        fid = frame.get("frame_id", "unknown")

        # Fetch validated GSAP labels from the stored HTML
        labels = await _extract_gsap_labels_from_storage(sb, goal_id, lesson_id, fid)
        animation_context = {"validated_labels": labels} if labels else None

        narrations = await generate_frame_narration(gemini, frame, animation_context)

        if narrations and len(narrations) == len(frame.get("steps", [])):
            for step, text in zip(frame["steps"], narrations):
                step["narration_spoken"] = text
            updated_count += 1
            avg = sum(len(t) for t in narrations) // len(narrations)
            results.append({"frame_id": fid, "status": "ok", "avg_chars": avg})
            logger.info(f"[NarrationRetry] {fid}: OK — {len(narrations)} steps, avg {avg} chars")
        else:
            results.append({"frame_id": fid, "status": "failed"})
            logger.warning(f"[NarrationRetry] {fid}: narration generation failed")

    # Save updated narrations back to course plan
    if updated_count:
        lesson["frames"] = frames
        lesson_plans[lesson_id] = lesson
        sb.table("course_plans").update(
            {"lesson_plans": lesson_plans},
        ).eq("goal_id", goal_id).execute()
        logger.info(f"[NarrationRetry] Saved {updated_count} frame narrations to course plan")

    return {
        "lesson_id": lesson_id,
        "frames_checked": len(frames),
        "frames_needing_narration": len(needs_narration),
        "frames_updated": updated_count,
        "results": results,
    }
