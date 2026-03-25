"""Animation Agent pipeline — generate Manim animations for a single lesson.

For each animation spec: search → codegen → render → validate (retry on error).
Uploads rendered MP4s to Supabase Storage.
"""

import logging
import os
import time
import traceback

from app.agents.animation.codegen import generate_manim_code, fix_manim_code
from app.agents.animation.data_prep import prepare_animation_data
from app.agents.animation.renderer import render_manim_scene
from app.agents.animation.search import search_manim_reference
from app.config import get_settings
from app.services.agent_task import (
    update_agent_task,
    fetch_course_plan,
    save_animation_result,
    cleanup_lesson_animations,
)

logger = logging.getLogger(__name__)

AGENT_TYPE = "visualization"


async def run_animation_pipeline(
    goal_id: str,
    user_id: str,
    lesson_id: str,
) -> None:
    """Generate all Manim animations for a single lesson."""
    try:
        settings = get_settings()

        await update_agent_task(
            goal_id,
            AGENT_TYPE,
            status="active",
            progress=0,
            current_task=f"Generating animations for lesson {lesson_id}...",
            log_message=f"Animation pipeline started for lesson {lesson_id}",
            log_level="system",
        )

        # Clean up previous animations for this lesson (retry scenario)
        await cleanup_lesson_animations(goal_id, lesson_id)

        # Fetch the course plan and extract animation specs for this lesson
        course_plan = await fetch_course_plan(goal_id)
        if not course_plan:
            raise ValueError("No course plan found — run course planner first")

        lesson_plans = course_plan.get("lesson_plans", {})
        lesson_plan = lesson_plans.get(lesson_id)
        if not lesson_plan:
            raise ValueError(f"Lesson '{lesson_id}' not found in course plan")

        # Collect all animation specs from all segments
        animation_specs = []
        for seg in lesson_plan.get("segments", []):
            for anim in seg.get("animations", []):
                anim["_segment_title"] = seg.get("title", "")
                animation_specs.append(anim)

        total = len(animation_specs)
        if total == 0:
            await update_agent_task(
                goal_id, AGENT_TYPE,
                status="completed", progress=100,
                current_task="No animations in this lesson",
                log_message=f"Lesson {lesson_id} has 0 animation specs — skipping",
            )
            return

        await update_agent_task(
            goal_id, AGENT_TYPE,
            current_task=f"Processing {total} animations for {lesson_id}...",
            log_message=f"Found {total} animation specs in lesson {lesson_id}",
        )

        # Process each animation sequentially (rendering is CPU-bound)
        output_dir = os.path.join(settings.manim_output_dir, goal_id, lesson_id)
        os.makedirs(output_dir, exist_ok=True)

        completed = 0
        failed = 0

        for i, spec in enumerate(animation_specs):
            anim_id = spec.get("animation_id", f"anim-{i}")
            anim_type = spec.get("animation_type", "unknown")
            seg_title = spec.get("_segment_title", "")

            progress = (i / total) * 100
            await update_agent_task(
                goal_id, AGENT_TYPE,
                progress=round(progress, 1),
                current_task=f"[{i+1}/{total}] {anim_type}: {seg_title[:50]}",
                focus=anim_id,
            )

            # Step 0: Prepare real data (download datasets if needed)
            prepared_data = None
            data_req = spec.get("data_requirements", "")
            if data_req:
                try:
                    data_dir = os.path.join(output_dir, "data", anim_id)
                    prepared_data = await prepare_animation_data(data_req, data_dir)
                    logger.info(f"Prepared data for {anim_id}: {prepared_data.get('dataset')}")
                except Exception as e:
                    logger.warning(f"Data prep failed for {anim_id}: {e}")

            # Step 1: Search for reference Manim code
            search_results = "No reference code found."
            if settings.animation_search_enabled:
                try:
                    search_results = await search_manim_reference(
                        animation_type=anim_type,
                        description=spec.get("description", ""),
                    )
                except Exception as e:
                    logger.warning(f"Search failed for {anim_id}: {e}")

            # Step 2-4: Generate → Render → Validate (with retries)
            success = False
            code = ""
            output_path = None
            output_url = None
            error_log = None
            render_time = 0.0

            for attempt in range(settings.animation_max_retries):
                try:
                    # Step 2: Generate Manim code
                    if attempt == 0:
                        code = await generate_manim_code(
                            animation_spec=spec,
                            search_results=search_results,
                            prepared_data=prepared_data,
                        )
                    else:
                        # Fix the broken code with error context
                        code = await fix_manim_code(
                            code=code,
                            error=error_log or "Unknown error",
                        )

                    # Step 3: Render
                    t = time.time()
                    output_path, render_error = await render_manim_scene(
                        code=code,
                        output_dir=output_dir,
                        quality=settings.animation_render_quality,
                    )
                    render_time = time.time() - t

                    # Step 4: Validate
                    if output_path and not render_error:
                        # Upload to Supabase Storage
                        output_url = await _upload_to_storage(
                            output_path, goal_id, lesson_id, anim_id,
                        )
                        success = True
                        break
                    else:
                        error_log = render_error
                        logger.warning(
                            f"Render failed for {anim_id} (attempt {attempt+1}): "
                            f"{render_error[:200] if render_error else 'unknown'}"
                        )

                except Exception as e:
                    error_log = str(e)
                    logger.warning(
                        f"Codegen failed for {anim_id} (attempt {attempt+1}): {e}"
                    )

            # Save result
            status = "completed" if success else "failed"
            await save_animation_result(
                goal_id=goal_id,
                user_id=user_id,
                lesson_id=lesson_id,
                animation_id=anim_id,
                animation_type=anim_type,
                status=status,
                manim_code=code,
                output_path=output_path or "",
                output_url=output_url or "",
                error_log=error_log if not success else None,
                render_time=render_time,
            )

            if success:
                completed += 1
                await update_agent_task(
                    goal_id, AGENT_TYPE,
                    log_message=(
                        f"[{i+1}/{total}] {anim_type} '{anim_id}' rendered "
                        f"({render_time:.1f}s)"
                    ),
                    log_level="success",
                )
            else:
                failed += 1
                await update_agent_task(
                    goal_id, AGENT_TYPE,
                    log_message=(
                        f"[{i+1}/{total}] {anim_type} '{anim_id}' FAILED after "
                        f"{settings.animation_max_retries} attempts"
                    ),
                    log_level="error",
                )

        # Complete
        await update_agent_task(
            goal_id,
            AGENT_TYPE,
            status="completed",
            progress=100,
            current_task=f"Animations complete: {completed}/{total} rendered",
            focus=None,
            log_message=(
                f"Animation pipeline for {lesson_id}: "
                f"{completed}/{total} completed, {failed} failed"
            ),
            log_level="success",
        )

    except Exception as e:
        logger.error(f"Animation pipeline failed: {traceback.format_exc()}")
        await update_agent_task(
            goal_id,
            AGENT_TYPE,
            status="failed",
            current_task="Pipeline failed",
            error_message=str(e)[:500],
            log_message=f"Animation pipeline error: {str(e)[:200]}",
            log_level="error",
        )


async def _upload_to_storage(
    local_path: str,
    goal_id: str,
    lesson_id: str,
    animation_id: str,
) -> str | None:
    """Upload rendered MP4 to Supabase Storage. Returns public URL or None."""
    try:
        from app.services.supabase import get_supabase
        settings = get_settings()

        sb = get_supabase()
        bucket = settings.animation_storage_bucket
        storage_path = f"{goal_id}/{lesson_id}/{animation_id}.mp4"

        with open(local_path, "rb") as f:
            sb.storage.from_(bucket).upload(
                storage_path,
                f.read(),
                file_options={"content-type": "video/mp4"},
            )

        # Get public URL
        url = sb.storage.from_(bucket).get_public_url(storage_path)
        logger.info(f"Uploaded to storage: {storage_path}")

        # Clean up local file
        try:
            os.unlink(local_path)
        except OSError:
            pass

        return url

    except Exception as e:
        logger.warning(f"Storage upload failed for {animation_id}: {e}")
        # Return local path as fallback
        return None
