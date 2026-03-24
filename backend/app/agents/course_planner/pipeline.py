"""Course Planner pipeline — 2-stage course plan generation.

Stage 1: STRUCTURE — break research into modules + lesson outlines (1 LLM call)
Stage 2: DETAIL   — generate teaching DAG per lesson (parallel LLM calls)
"""

import asyncio
import logging
import traceback

from app.agents.course_planner.structure import run_structure_stage
from app.agents.course_planner.lesson_detail import run_lesson_detail
from app.agents.model_pool import ModelPool
from app.agents.progress import ParallelProgressTracker
from app.agents.rate_limiter import get_rate_limiter
from app.config import get_settings
from app.models.course_plan import LessonOutline, LessonPlan, ResourceReference
from app.services.agent_task import (
    fetch_onboarding_data,
    fetch_research_results,
    fetch_research_sources,
    save_course_plan,
    cleanup_previous_course_plan,
    update_agent_task,
)

logger = logging.getLogger(__name__)

AGENT_TYPE = "planning"


async def run_course_planner_pipeline(goal_id: str, user_id: str) -> None:
    """Full 2-stage course planner pipeline."""
    try:
        settings = get_settings()

        # ── Initialize model pool ──
        pool_configs = settings.get_planner_pool_configs()
        model_pool: ModelPool | None = None
        if pool_configs:
            rate_limiter = await get_rate_limiter()
            for cfg in pool_configs:
                rate_limiter.register(cfg)
            model_pool = ModelPool(pool_configs)
            logger.info(
                f"Planner model pool: {[c.name for c in pool_configs]} "
                f"(max {settings.planner_max_parallel_lessons} parallel lessons)"
            )

        # Mark as active
        await update_agent_task(
            goal_id,
            AGENT_TYPE,
            status="active",
            progress=0,
            current_task="Starting course planner...",
            log_message="Course planner pipeline started",
            log_level="system",
        )

        # Clean up any previous course plan (retry scenario)
        await cleanup_previous_course_plan(goal_id)

        # Fetch input data
        onboarding_data = await fetch_onboarding_data(goal_id, user_id)
        research_results = await fetch_research_results(goal_id)
        if not research_results:
            raise ValueError("No research results found — run research agent first")

        research_sources = await fetch_research_sources(goal_id)
        goal_title = onboarding_data["goal"].get("title", "Unknown goal")

        # ===== STAGE 1: STRUCTURE (0-25%) =====
        await update_agent_task(
            goal_id,
            AGENT_TYPE,
            progress=5,
            current_task="Designing course structure...",
            focus="structure",
            log_message=f"Generating course structure for: {goal_title}",
        )

        course_structure = await run_structure_stage(onboarding_data, research_results)

        # Collect all lessons for Stage 2
        all_lessons: list[LessonOutline] = []
        for module in course_structure.modules:
            all_lessons.extend(module.lessons)

        total_lessons = len(all_lessons)
        total_modules = len(course_structure.modules)

        await update_agent_task(
            goal_id,
            AGENT_TYPE,
            progress=25,
            current_task=(
                f"Course structure: {total_modules} modules, {total_lessons} lessons"
            ),
            log_message=(
                f"Structure complete: {total_modules} modules, {total_lessons} lessons, "
                f"~{course_structure.total_estimated_minutes}min total"
            ),
            log_level="success",
        )

        # ===== STAGE 2: DETAIL (25-95%) =====
        lesson_plans: dict[str, LessonPlan] = {}
        student_resource_map: dict[str, list[ResourceReference]] = {}

        # ── Parallel lesson detail (semaphore-gated, works with or without pool) ──
        lesson_semaphore = asyncio.Semaphore(settings.planner_max_parallel_lessons)
        progress_tracker = ParallelProgressTracker(
            total=total_lessons,
            range_start=25.0,
            range_end=95.0,
            goal_id=goal_id,
            agent_type=AGENT_TYPE,
        )

        pool_desc = f"across {model_pool.model_count} models" if model_pool else f"({settings.planner_detail_model})"
        await update_agent_task(
            goal_id,
            AGENT_TYPE,
            progress=25,
            current_task=f"Generating {total_lessons} lesson plans {pool_desc}...",
            focus="detail",
            log_message=f"Starting parallel lesson detail for {total_lessons} lessons {pool_desc}",
        )

        async def detail_one_lesson(
            i: int, lesson: LessonOutline,
        ) -> tuple[str, LessonPlan | None, list[ResourceReference]]:
            async with lesson_semaphore:
                await progress_tracker.report_start(lesson.title, i)

                # Retry up to 2 attempts for validation failures
                last_error = None
                for attempt in range(2):
                    try:
                        if model_pool:
                            async def _detail_with_model(
                                model_str: str, _lesson=lesson,
                            ) -> tuple[LessonPlan, list[ResourceReference]]:
                                return await run_lesson_detail(
                                    lesson=_lesson,
                                    research_sources=research_sources,
                                    research_results=research_results,
                                    onboarding_data=onboarding_data,
                                    goal_id=goal_id,
                                    user_id=user_id,
                                    model_string=model_str,
                                )
                            plan, refs = await model_pool.run_with_pool(_detail_with_model)
                        else:
                            plan, refs = await run_lesson_detail(
                                lesson=lesson,
                                research_sources=research_sources,
                                research_results=research_results,
                                onboarding_data=onboarding_data,
                                goal_id=goal_id,
                                user_id=user_id,
                            )

                        await progress_tracker.mark_completed(
                            lesson.title,
                            success=True,
                            detail=(
                                f"{len(plan.segments)} segments, "
                                f"{plan.total_animations} animations"
                            ),
                        )
                        return lesson.lesson_id, plan, refs
                    except Exception as e:
                        last_error = e
                        if attempt == 0:
                            logger.warning(
                                f"Lesson '{lesson.title}' attempt 1 failed: {e}, retrying..."
                            )
                            continue

                logger.error(
                    f"Lesson detail failed for '{lesson.title}' after 2 attempts: {last_error}"
                )
                await progress_tracker.mark_completed(
                    lesson.title,
                    success=False,
                    detail=str(last_error)[:100],
                )
                return lesson.lesson_id, None, []

        parallel_results = await asyncio.gather(
            *[detail_one_lesson(i, les) for i, les in enumerate(all_lessons)]
        )

        for lesson_id, plan, refs in parallel_results:
            if plan is not None:
                lesson_plans[lesson_id] = plan
            if refs:
                student_resource_map[lesson_id] = refs

        # ===== SAVE & COMPLETE (95-100%) =====
        await update_agent_task(
            goal_id,
            AGENT_TYPE,
            progress=96,
            current_task="Saving course plan...",
            log_message=f"Saving {len(lesson_plans)} lesson plans",
        )

        # Serialize for storage
        course_structure_dict = course_structure.model_dump()
        lesson_plans_dict = {
            lid: plan.model_dump() for lid, plan in lesson_plans.items()
        }
        resource_map_dict = {
            lid: [r.model_dump() for r in refs]
            for lid, refs in student_resource_map.items()
        }

        await save_course_plan(
            goal_id=goal_id,
            user_id=user_id,
            course_structure=course_structure_dict,
            lesson_plans=lesson_plans_dict,
            student_resource_map=resource_map_dict,
            total_lessons=total_lessons,
            total_modules=total_modules,
            total_estimated_minutes=course_structure.total_estimated_minutes,
        )

        total_segments = sum(len(p.segments) for p in lesson_plans.values())
        total_animations = sum(p.total_animations for p in lesson_plans.values())
        total_interactions = sum(p.total_interactions for p in lesson_plans.values())

        await update_agent_task(
            goal_id,
            AGENT_TYPE,
            status="completed",
            progress=100,
            current_task="Course plan complete!",
            focus=None,
            log_message=(
                f"Course planner completed. "
                f"{total_modules} modules, {total_lessons} lessons, "
                f"{total_segments} segments, {total_animations} animations, "
                f"{total_interactions} interactions"
            ),
            log_level="success",
        )

    except Exception as e:
        logger.error(f"Course planner pipeline failed: {traceback.format_exc()}")
        await update_agent_task(
            goal_id,
            AGENT_TYPE,
            status="failed",
            current_task="Pipeline failed",
            error_message=str(e)[:500],
            log_message=f"Pipeline error: {str(e)[:200]}",
            log_level="error",
        )
