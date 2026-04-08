"""Full-pipeline orchestrator: research → course planner → animations.

Runs the entire learning-content generation pipeline as one background task.
Each stage updates its own agent_tasks row so the frontend reflects accurate
state in realtime. If a stage fails, downstream stages are marked failed too.
"""

import asyncio
import logging

from app.agents.research_v3 import run_research_v3
from app.agents.course_planner.pipeline_v4 import run_course_planner_v4
from app.agents.animation_v2.pipeline import generate_lesson_visuals
from app.services.agent_task import fetch_course_plan, update_agent_task

logger = logging.getLogger(__name__)

# Max number of lessons being animated concurrently. Animation pipeline
# already batches frames within a lesson; this caps cross-lesson concurrency
# to avoid overwhelming LLM rate limits.
ANIMATION_CONCURRENCY = 2


async def run_full_pipeline(goal_id: str, user_id: str) -> None:
    """Run the full pipeline end-to-end. Idempotent + fault-tolerant."""
    logger.info(f"[Pipeline] Starting full pipeline for goal {goal_id}")

    # ── Stage 1: Research ──
    try:
        await run_research_v3(goal_id, user_id)
    except Exception as e:
        logger.error(f"[Pipeline] Research failed for {goal_id}: {e}")
        await _mark_downstream_failed(
            goal_id, f"Research failed: {str(e)[:200]}"
        )
        return

    # ── Stage 2: Course Planner ──
    try:
        await run_course_planner_v4(goal_id, user_id)
    except Exception as e:
        logger.error(f"[Pipeline] Course planner failed for {goal_id}: {e}")
        try:
            await update_agent_task(
                goal_id, "planning", status="failed",
                error_message=str(e)[:200],
            )
        except Exception:
            pass
        try:
            await update_agent_task(
                goal_id, "visualization", status="failed",
                error_message="Course planning failed",
            )
        except Exception:
            pass
        return

    # ── Stage 3: Animations (per lesson, parallel with semaphore) ──
    course_plan = await fetch_course_plan(goal_id)
    if not course_plan:
        logger.error(f"[Pipeline] No course plan found after planning stage for {goal_id}")
        await update_agent_task(
            goal_id, "visualization", status="failed",
            error_message="Course plan not found after planning",
        )
        return

    lesson_plans = course_plan.get("lesson_plans", {}) or {}
    # Only animate lessons that have frames and didn't error out during planning
    ready_lessons = [
        lid for lid, lp in lesson_plans.items()
        if isinstance(lp, dict) and lp.get("frames") and not lp.get("error")
    ]

    if not ready_lessons:
        logger.warning(f"[Pipeline] No ready lessons to animate for {goal_id}")
        await update_agent_task(
            goal_id, "visualization", status="failed",
            error_message="No lessons available to animate",
        )
        return

    await update_agent_task(
        goal_id, "visualization",
        status="active",
        progress=2,
        current_task=f"Generating visuals for {len(ready_lessons)} lessons...",
    )

    semaphore = asyncio.Semaphore(ANIMATION_CONCURRENCY)
    completed_count = 0
    failed_count = 0
    total = len(ready_lessons)

    async def _animate_one(lesson_id: str) -> None:
        nonlocal completed_count, failed_count
        async with semaphore:
            try:
                logger.info(f"[Pipeline] Animating lesson {lesson_id}")
                await generate_lesson_visuals(goal_id, user_id, lesson_id)
                completed_count += 1
            except Exception as e:
                failed_count += 1
                logger.error(
                    f"[Pipeline] Animation failed for lesson {lesson_id}: {e}"
                )
            finally:
                done = completed_count + failed_count
                pct = int(100 * done / total)
                try:
                    await update_agent_task(
                        goal_id, "visualization",
                        progress=pct,
                        current_task=(
                            f"{completed_count}/{total} lessons animated"
                            + (f" ({failed_count} failed)" if failed_count else "")
                        ),
                    )
                except Exception:
                    pass

    await asyncio.gather(
        *[_animate_one(lid) for lid in ready_lessons],
        return_exceptions=True,
    )

    # ── Final visualization status ──
    if completed_count == total:
        await update_agent_task(
            goal_id, "visualization",
            status="completed",
            progress=100,
            current_task=f"All {completed_count} lessons animated",
        )
    elif completed_count > 0:
        await update_agent_task(
            goal_id, "visualization",
            status="completed",
            progress=100,
            current_task=(
                f"{completed_count}/{total} lessons animated "
                f"({failed_count} failed)"
            ),
        )
    else:
        await update_agent_task(
            goal_id, "visualization",
            status="failed",
            error_message=f"All {total} lessons failed to animate",
        )

    logger.info(
        f"[Pipeline] Done for {goal_id}: {completed_count}/{total} animated"
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
            logger.warning(
                f"[Pipeline] Could not mark {agent_type} as failed: {e}"
            )
