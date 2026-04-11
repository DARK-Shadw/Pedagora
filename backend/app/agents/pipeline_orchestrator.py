"""Full-pipeline orchestrator: research → structure → per-lesson (storyboard + animation).

Each lesson is fully completed (storyboard then animation) before the next
lesson starts, so the user can watch progress lesson by lesson in real time.

Each stage updates its own agent_tasks row so the frontend reflects accurate
state. If a stage fails, downstream stages are marked failed too.
"""

import logging

from app.agents.research_v3 import run_research_v3
from app.agents.course_planner.pipeline_v4 import (
    generate_course_structure_v4,
    generate_one_lesson_storyboard_v4,
)
from app.agents.animation_v2.pipeline import generate_lesson_visuals
from app.services.agent_task import (
    update_agent_task,
    fetch_course_plan,
    fetch_research_results,
    fetch_onboarding_data,
    get_lesson_animations,
)

logger = logging.getLogger(__name__)


async def run_full_pipeline(goal_id: str, user_id: str) -> None:
    """Run the full pipeline end-to-end. Idempotent + fault-tolerant."""
    logger.info(f"[Pipeline] Starting full pipeline for goal {goal_id}")

    # ── Stage 1: Research ──
    try:
        await run_research_v3(goal_id, user_id)
    except Exception as e:
        logger.error(f"[Pipeline] Research failed for {goal_id}: {e}")
        await _mark_downstream_failed(goal_id, f"Research failed: {str(e)[:200]}")
        return

    # ── Stage 2a: Course Structure ──
    # Orchestrator owns started_at for the planning task.
    await update_agent_task(
        goal_id, "planning",
        status="active",
        progress=2,
        current_task="Designing course structure...",
        log_message="Planning agent started",
    )

    try:
        struct = await generate_course_structure_v4(goal_id, user_id)
    except Exception as e:
        logger.error(f"[Pipeline] Structure generation failed for {goal_id}: {e}")
        await update_agent_task(
            goal_id, "planning",
            status="failed",
            error_message=f"Structure failed: {str(e)[:200]}",
        )
        await update_agent_task(
            goal_id, "visualization",
            status="failed",
            error_message="Course planning failed",
        )
        return

    all_lessons = struct["all_lessons"]
    context = struct["context"]
    total = len(all_lessons)

    if not total:
        await update_agent_task(
            goal_id, "planning",
            status="failed",
            error_message="No lessons in generated course structure",
        )
        await update_agent_task(
            goal_id, "visualization",
            status="failed",
            error_message="No lessons to animate",
        )
        return

    # Mark visualization active now — interleaved work starts this lesson
    await update_agent_task(
        goal_id, "visualization",
        status="active",
        progress=0,
        current_task=f"Waiting for first lesson storyboard...",
        log_message=f"Visualization agent started — {total} lessons queued",
    )

    plan_done = 0
    plan_failed = 0
    anim_done = 0
    anim_failed = 0

    # ── Stage 2b + 3: interleaved per-lesson (storyboard → animation) ──
    for i, lesson in enumerate(all_lessons):
        lesson_id = lesson.get("lesson_id", f"lesson-{i}")
        lesson_title = lesson.get("title", lesson_id)[:40]

        # ── Storyboard for this lesson ──
        storyboard_ok = False
        try:
            pct = 15 + int(75 * i / total)
            lp = await generate_one_lesson_storyboard_v4(
                goal_id=goal_id,
                user_id=user_id,
                lesson=lesson,
                context=context,
                overall_pct=pct,
            )
            if lp.get("frames") and not lp.get("error"):
                plan_done += 1
                storyboard_ok = True
            else:
                plan_failed += 1
                logger.warning(
                    f"[Pipeline] Storyboard {lesson_id} completed with error: "
                    f"{lp.get('error', 'no frames')}"
                )
        except Exception as e:
            plan_failed += 1
            logger.error(f"[Pipeline] Storyboard {lesson_id} crashed: {e}")

        await update_agent_task(
            goal_id, "planning",
            progress=15 + int(75 * (i + 1) / total),
            current_task=f"Storyboards: {plan_done + plan_failed}/{total} — {plan_done} ready",
        )

        if not storyboard_ok:
            # Still update visualization progress so the bar doesn't freeze
            await update_agent_task(
                goal_id, "visualization",
                progress=int(100 * (i + 1) / total),
                current_task=(
                    f"{anim_done}/{total} animated"
                    + (f" ({anim_failed} failed)" if anim_failed else "")
                    + f" — lesson {i + 1} storyboard failed, skipped"
                ),
            )
            continue  # Skip animation for this lesson

        # ── Animation for this lesson ──
        try:
            logger.info(f"[Pipeline] Animating lesson {lesson_id}: {lesson_title}")
            await generate_lesson_visuals(goal_id, user_id, lesson_id)
            anim_done += 1
        except Exception as e:
            anim_failed += 1
            logger.error(f"[Pipeline] Animation {lesson_id} crashed: {e}")

        await update_agent_task(
            goal_id, "visualization",
            progress=int(100 * (i + 1) / total),
            current_task=(
                f"{anim_done}/{total} animated"
                + (f" ({anim_failed} failed)" if anim_failed else "")
            ),
        )

    # ── Final planning status ──
    if plan_done > 0:
        await update_agent_task(
            goal_id, "planning",
            status="completed",
            progress=100,
            current_task=(
                f"All done — {plan_done}/{total} storyboards"
                + (f" ({plan_failed} failed)" if plan_failed else "")
            ),
            log_message=f"Planning complete: {plan_done}/{total} lessons",
        )
    else:
        await update_agent_task(
            goal_id, "planning",
            status="failed",
            error_message=f"All {total} storyboards failed",
        )

    # ── Final visualization status ──
    if anim_done > 0:
        await update_agent_task(
            goal_id, "visualization",
            status="completed",
            progress=100,
            current_task=(
                f"All done — {anim_done}/{total} lessons animated"
                + (f" ({anim_failed} failed)" if anim_failed else "")
            ),
            log_message=f"Visualization complete: {anim_done}/{total} lessons",
        )
    else:
        await update_agent_task(
            goal_id, "visualization",
            status="failed",
            error_message=f"All {total} lessons failed to animate",
        )

    logger.info(
        f"[Pipeline] Done for {goal_id}: "
        f"storyboards {plan_done}/{total}, animations {anim_done}/{total}"
    )


async def resume_pipeline(goal_id: str, user_id: str) -> None:
    """Smart resume — picks up from wherever the pipeline left off.

    Checks what's already done (storyboards + animations) and only runs
    what's missing, sequentially per lesson:
      - No course_structure → run structure first
      - Lesson missing storyboard → generate storyboard + animation
      - Lesson has storyboard but no/incomplete animations → animate only
      - Both done → skip
    """
    logger.info(f"[Pipeline] Resuming pipeline for goal {goal_id}")

    # ── Load current state ──
    course_plan = await fetch_course_plan(goal_id)
    course_structure = (course_plan or {}).get("course_structure")
    lesson_plans: dict = (course_plan or {}).get("lesson_plans") or {}

    # If no structure at all, we need context to build it
    context: dict | None = None

    if not course_structure:
        logger.info(f"[Pipeline] No course structure — running structure stage")
        await update_agent_task(
            goal_id, "planning",
            status="active", progress=2,
            current_task="Designing course structure...",
            log_message="Resume: generating course structure",
        )
        try:
            struct = await generate_course_structure_v4(goal_id, user_id)
            course_structure = struct["course_structure"]
            context = struct["context"]
        except Exception as e:
            logger.error(f"[Pipeline] Resume: structure failed: {e}")
            await update_agent_task(goal_id, "planning", status="failed",
                                    error_message=f"Structure failed: {str(e)[:200]}")
            await update_agent_task(goal_id, "visualization", status="failed",
                                    error_message="Course planning failed")
            return
    else:
        # Build context from existing onboarding + research (needed for storyboard prompts)
        try:
            from app.agents.course_planner.pipeline_v4 import (
                _build_research_context,
                _flatten_lessons,
            )
            onboarding = await fetch_onboarding_data(goal_id, user_id)
            research_results = await fetch_research_results(goal_id)
            from app.services.agent_task import fetch_research_sources
            research_sources = await fetch_research_sources(goal_id)
            research_ctx = _build_research_context(research_results or {}, research_sources)

            from app.services.supabase import get_supabase
            sb = get_supabase()
            student_name = "Student"
            try:
                prof = sb.table("profiles").select("name, email").eq("id", user_id).single().execute()
                if prof.data:
                    student_name = (
                        prof.data.get("name")
                        or (prof.data.get("email") or "").split("@")[0]
                        or "Student"
                    )
            except Exception:
                pass

            context = {
                "goal": onboarding.get("goal") or {},
                "prefs": onboarding.get("preferences") or {},
                "profile": onboarding.get("profile") or {},
                "student_name": student_name,
                "research_ctx": research_ctx,
                "research_sources": research_sources,
            }
        except Exception as e:
            logger.error(f"[Pipeline] Resume: context load failed: {e}")
            await update_agent_task(goal_id, "planning", status="failed",
                                    error_message=f"Could not load research context: {str(e)[:200]}")
            return

    from app.agents.course_planner.pipeline_v4 import _flatten_lessons
    all_lessons = _flatten_lessons(course_structure)
    total = len(all_lessons)

    if not total:
        await update_agent_task(goal_id, "planning", status="failed",
                                error_message="No lessons in course structure")
        return

    # ── Determine what's done ──
    async def _storyboard_done(lid: str) -> bool:
        lp = lesson_plans.get(lid)
        return bool(
            isinstance(lp, dict)
            and lp.get("frames")
            and len(lp["frames"]) > 0
            and not lp.get("error")
        )

    async def _animations_done(lid: str) -> bool:
        lp = lesson_plans.get(lid, {})
        expected = len((lp or {}).get("frames") or [])
        if expected == 0:
            return False
        anims = await get_lesson_animations(goal_id, lid)
        completed = sum(1 for a in anims if a.get("status") == "completed")
        return completed >= expected

    # Activate both task rows
    await update_agent_task(goal_id, "planning", status="active", progress=2,
                            current_task="Resuming pipeline — checking progress...",
                            log_message="Pipeline resumed")
    await update_agent_task(goal_id, "visualization", status="active", progress=0,
                            current_task="Resuming pipeline...")

    plan_done = 0
    plan_skipped = 0
    anim_done = 0
    anim_skipped = 0
    plan_failed = 0
    anim_failed = 0

    for i, lesson in enumerate(all_lessons):
        lesson_id = lesson.get("lesson_id", f"lesson-{i}")

        sb_done = await _storyboard_done(lesson_id)
        an_done = await _animations_done(lesson_id)

        if sb_done and an_done:
            plan_skipped += 1
            anim_skipped += 1
            logger.info(f"[Pipeline] Resume: {lesson_id} fully done — skipping")
            await update_agent_task(
                goal_id, "planning",
                progress=int(90 * (i + 1) / total),
                current_task=f"Resuming: {i + 1}/{total} — {lesson_id} already complete",
            )
            await update_agent_task(
                goal_id, "visualization",
                progress=int(100 * (i + 1) / total),
                current_task=f"Resuming: {i + 1}/{total} — {lesson_id} already complete",
            )
            continue

        # ── Storyboard if missing ──
        if not sb_done:
            try:
                pct = 15 + int(75 * i / total)
                lp = await generate_one_lesson_storyboard_v4(
                    goal_id=goal_id,
                    user_id=user_id,
                    lesson=lesson,
                    context=context,
                    overall_pct=pct,
                )
                # Refresh lesson_plans after save
                lesson_plans[lesson_id] = lp
                if lp.get("frames") and not lp.get("error"):
                    plan_done += 1
                    sb_done = True
                else:
                    plan_failed += 1
            except Exception as e:
                plan_failed += 1
                logger.error(f"[Pipeline] Resume: storyboard {lesson_id} crashed: {e}")
        else:
            plan_skipped += 1

        await update_agent_task(
            goal_id, "planning",
            progress=15 + int(75 * (i + 1) / total),
            current_task=f"Storyboards: {plan_done + plan_skipped}/{total} ready",
        )

        # ── Animation if storyboard exists but animations are missing ──
        if sb_done and not an_done:
            try:
                await generate_lesson_visuals(goal_id, user_id, lesson_id)
                anim_done += 1
            except Exception as e:
                anim_failed += 1
                logger.error(f"[Pipeline] Resume: animation {lesson_id} crashed: {e}")
        elif an_done:
            anim_skipped += 1

        await update_agent_task(
            goal_id, "visualization",
            progress=int(100 * (i + 1) / total),
            current_task=(
                f"{anim_done + anim_skipped}/{total} animated"
                + (f" ({anim_failed} failed)" if anim_failed else "")
            ),
        )

    # ── Final status ──
    total_plan_ok = plan_done + plan_skipped
    total_anim_ok = anim_done + anim_skipped

    if total_plan_ok == total:
        await update_agent_task(
            goal_id, "planning", status="completed", progress=100,
            current_task=f"All {total} storyboards done"
            + (f" ({plan_done} new)" if plan_done else ""),
            log_message=f"Planning complete: {total_plan_ok}/{total}",
        )
    else:
        await update_agent_task(
            goal_id, "planning", status="failed",
            error_message=f"{plan_failed}/{total} storyboards failed",
        )

    if total_anim_ok == total:
        await update_agent_task(
            goal_id, "visualization", status="completed", progress=100,
            current_task=f"All {total} lessons animated"
            + (f" ({anim_done} new)" if anim_done else ""),
            log_message=f"Visualization complete: {total_anim_ok}/{total}",
        )
    else:
        await update_agent_task(
            goal_id, "visualization", status="failed",
            error_message=f"{anim_failed}/{total} animations failed",
        )

    logger.info(
        f"[Pipeline] Resume done for {goal_id}: "
        f"storyboards {total_plan_ok}/{total} ({plan_done} new), "
        f"animations {total_anim_ok}/{total} ({anim_done} new)"
    )


async def _mark_downstream_failed(goal_id: str, reason: str) -> None:
    """Mark planning + visualization as failed when an upstream stage fails."""
    for agent_type in ("planning", "visualization"):
        try:
            await update_agent_task(
                goal_id, agent_type,
                status="failed",
                error_message=reason,
            )
        except Exception as e:
            logger.warning(f"[Pipeline] Could not mark {agent_type} failed: {e}")
