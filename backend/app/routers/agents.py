from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from pydantic import BaseModel

from app.auth.dependencies import get_current_user
from app.models.requests import ResearchRequest, CoursePlanRequest, AnimateLessonRequest, RegenerateFrameRequest
from app.models.responses import ResearchAccepted, CoursePlanAccepted, AnimateLessonAccepted, RegenerateFrameAccepted, AgentStatusResponse
from app.services.agent_task import get_agent_task, update_agent_task, cleanup_previous_research, fetch_research_results, fetch_course_plan, get_lesson_animations
from app.agents.research_v3 import run_research_v3
from app.agents.course_planner.pipeline_v4 import run_course_planner_v4
from app.agents.pipeline_orchestrator import run_full_pipeline, resume_pipeline, ensure_storyboard_and_animate
from app.agents.episode_planner import run_episode_planner

router = APIRouter()


@router.post("/research", status_code=status.HTTP_202_ACCEPTED, response_model=ResearchAccepted)
async def trigger_research(
    request: ResearchRequest,
    background_tasks: BackgroundTasks,
    user: dict = Depends(get_current_user),
):
    """Trigger the FULL pipeline (research → course planner → animations).

    Returns 202 immediately. The full chain runs in the background as one task.
    Each stage updates its own agent_tasks row, so the frontend reflects
    accurate state via Supabase realtime.
    """
    user_id = user["sub"]
    goal_id = request.goal_id

    # Verify the research task exists and belongs to user
    task = await get_agent_task(goal_id, "research")

    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Research task not found for this goal",
        )

    if task.get("user_id") != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to trigger this task",
        )

    if task.get("status") not in ("queued", "failed"):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Task is already {task.get('status')}. Only queued or failed tasks can be triggered.",
        )

    # Reset all downstream tasks too so a retry runs the full chain cleanly
    if task.get("status") == "failed":
        for agent_type in ("research", "planning", "visualization"):
            try:
                await update_agent_task(
                    goal_id,
                    agent_type,
                    status="queued",
                    progress=0,
                    current_task=None,
                    error_message=None,
                    log_message=f"{agent_type} reset for retry",
                    log_level="system",
                )
            except Exception:
                # Ignore tasks that don't exist (some users may not have all 4 task rows)
                pass

    # Launch the full pipeline in background
    background_tasks.add_task(run_full_pipeline, goal_id, user_id)

    return ResearchAccepted(goal_id=goal_id, task_id=task["id"])


@router.post("/plan-episode", status_code=status.HTTP_202_ACCEPTED)
async def trigger_episode_planner(
    request: CoursePlanRequest,
    background_tasks: BackgroundTasks,
    user: dict = Depends(get_current_user),
):
    """Trigger single-episode planner (Gemini). Skips research entirely.

    If planning already completed but visualization didn't, only re-runs animations.
    """
    from app.agents.episode_planner import _run_episode_animations

    user_id = user["sub"]
    goal_id = request.goal_id

    task = await get_agent_task(goal_id, "planning")
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Planning task not found for this goal",
        )
    if task.get("user_id") != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized",
        )

    # If planning done but visualization incomplete → just run animations
    if task.get("status") == "completed":
        viz_task = await get_agent_task(goal_id, "visualization")
        if viz_task and viz_task.get("status") == "completed":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Episode already fully completed",
            )
        # Get frame count from course plan
        course_plan = await fetch_course_plan(goal_id)
        frame_count = len((course_plan or {}).get("lesson_plans", {}).get("mod1-les1", {}).get("frames", []))
        background_tasks.add_task(_run_episode_animations, goal_id, user_id, frame_count or 15)
        return {"goal_id": goal_id, "task_id": task["id"], "message": "Animation generation started"}

    if task.get("status") in ("failed", "active", "queued"):
        await update_agent_task(
            goal_id, "planning",
            status="queued", progress=0,
            current_task=None, error_message=None,
            log_message="Episode planner reset for retry",
            log_level="system",
        )

    background_tasks.add_task(run_episode_planner, goal_id, user_id)
    return {"goal_id": goal_id, "task_id": task["id"], "message": "Episode planner started"}


@router.post("/course-plan", status_code=status.HTTP_202_ACCEPTED, response_model=CoursePlanAccepted)
async def trigger_course_plan(
    request: CoursePlanRequest,
    background_tasks: BackgroundTasks,
    user: dict = Depends(get_current_user),
):
    """Trigger the course planner pipeline. Requires completed research."""
    user_id = user["sub"]
    goal_id = request.goal_id

    # Verify the planning task exists and belongs to user
    task = await get_agent_task(goal_id, "planning")
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Planning task not found for this goal",
        )
    if task.get("user_id") != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to trigger this task",
        )
    if task.get("status") not in ("queued", "failed"):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Task is already {task.get('status')}. Only queued or failed tasks can be triggered.",
        )

    # Verify research is completed
    research = await fetch_research_results(goal_id)
    if not research:
        raise HTTPException(
            status_code=status.HTTP_412_PRECONDITION_FAILED,
            detail="Research must be completed before running course planner",
        )

    # Reset task state for retries
    if task.get("status") == "failed":
        await update_agent_task(
            goal_id,
            "planning",
            status="queued",
            progress=0,
            current_task=None,
            error_message=None,
            log_message="Task reset for retry",
            log_level="system",
        )

    background_tasks.add_task(run_course_planner_v4, goal_id, user_id)
    return CoursePlanAccepted(goal_id=goal_id, task_id=task["id"])


@router.post("/continue-pipeline", status_code=status.HTTP_202_ACCEPTED)
async def continue_pipeline_endpoint(
    request: CoursePlanRequest,
    background_tasks: BackgroundTasks,
    user: dict = Depends(get_current_user),
):
    """Resume the pipeline from wherever it left off.

    Inspects existing course_plans + lesson_animations to determine what's
    already done, then runs only the missing steps in order:
    storyboard(L) → animation(L) for each incomplete lesson.
    """
    goal_id = request.goal_id
    user_id = user["sub"]

    # Verify the goal belongs to the user
    planning_task = await get_agent_task(goal_id, "planning")
    if not planning_task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Planning task not found for this goal",
        )
    if planning_task.get("user_id") != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized",
        )

    # Don't resume if already actively running
    if planning_task.get("status") == "active":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Pipeline is already running",
        )

    # Reset failed tasks to queued so the UI reflects the restart
    for agent_type in ("planning", "visualization"):
        t = await get_agent_task(goal_id, agent_type)
        if t and t.get("status") in ("failed", "completed"):
            await update_agent_task(
                goal_id, agent_type,
                status="queued",
                progress=0,
                current_task=None,
                error_message=None,
                log_message="Pipeline resumed by user",
                log_level="system",
            )

    background_tasks.add_task(resume_pipeline, goal_id, user_id)
    return {"goal_id": goal_id, "status": "resumed"}


@router.post("/animate-lesson", status_code=status.HTTP_202_ACCEPTED, response_model=AnimateLessonAccepted)
async def trigger_animate_lesson(
    request: AnimateLessonRequest,
    background_tasks: BackgroundTasks,
    user: dict = Depends(get_current_user),
):
    """Trigger animation generation for a single lesson. Requires completed course plan."""
    user_id = user["sub"]
    goal_id = request.goal_id
    lesson_id = request.lesson_id

    # Verify course plan exists
    course_plan = await fetch_course_plan(goal_id)
    if not course_plan:
        raise HTTPException(
            status_code=status.HTTP_412_PRECONDITION_FAILED,
            detail="Course plan must be completed before generating animations",
        )

    # Verify lesson exists in the plan
    lesson_plans = course_plan.get("lesson_plans", {})
    if lesson_id not in lesson_plans:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Lesson '{lesson_id}' not found in course plan",
        )

    background_tasks.add_task(ensure_storyboard_and_animate, goal_id, user_id, lesson_id)
    return AnimateLessonAccepted(goal_id=goal_id, lesson_id=lesson_id)


@router.post("/regenerate-frame", status_code=status.HTTP_202_ACCEPTED, response_model=RegenerateFrameAccepted)
async def trigger_regenerate_frame(
    request: RegenerateFrameRequest,
    background_tasks: BackgroundTasks,
    user: dict = Depends(get_current_user),
):
    """Regenerate a single animation frame. Deletes existing output and re-runs."""
    from app.agents.animation_v2.pipeline import regenerate_single_frame

    user_id = user["sub"]
    goal_id = request.goal_id
    lesson_id = request.lesson_id
    frame_id = request.frame_id

    # Verify course plan exists and contains the frame
    course_plan = await fetch_course_plan(goal_id)
    if not course_plan:
        raise HTTPException(
            status_code=status.HTTP_412_PRECONDITION_FAILED,
            detail="Course plan must exist before regenerating frames",
        )
    lesson_plans = course_plan.get("lesson_plans", {})
    lesson = lesson_plans.get(lesson_id, {})
    if not lesson:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Lesson '{lesson_id}' not found in course plan",
        )
    frames = lesson.get("frames", [])
    if not any(f.get("frame_id") == frame_id for f in frames):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Frame '{frame_id}' not found in lesson '{lesson_id}'",
        )

    background_tasks.add_task(regenerate_single_frame, goal_id, user_id, lesson_id, frame_id)
    return RegenerateFrameAccepted(goal_id=goal_id, lesson_id=lesson_id, frame_id=frame_id)


@router.get("/course-plan/{goal_id}")
async def get_course_plan_endpoint(
    goal_id: str,
    user: dict = Depends(get_current_user),
):
    """Fetch the course plan for a goal."""
    plan = await fetch_course_plan(goal_id)
    if not plan:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Course plan not found")
    if plan.get("user_id") != user["sub"]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized")
    return plan


@router.get("/animation-status/{goal_id}/{lesson_id}")
async def get_animation_status(
    goal_id: str,
    lesson_id: str,
    user: dict = Depends(get_current_user),
):
    """Get animation generation status for a lesson."""
    animations = await get_lesson_animations(goal_id, lesson_id)
    return {
        "goal_id": goal_id,
        "lesson_id": lesson_id,
        "total": len(animations),
        "completed": sum(1 for a in animations if a["status"] == "completed"),
        "failed": sum(1 for a in animations if a["status"] == "failed"),
        "pending": sum(1 for a in animations if a["status"] == "pending"),
        "animations": animations,
    }


class AssessmentRequest(BaseModel):
    goal_title: str
    education_level: str = "self_learner"
    prerequisites: list[dict] = []


@router.post("/generate-assessment")
async def generate_assessment(request: AssessmentRequest):
    """Generate skill assessment questions using Groq."""
    import json
    import httpx
    from app.config import get_settings

    settings = get_settings()
    groq_key = settings.groq_api_key
    if not groq_key:
        raise HTTPException(status_code=500, detail="Groq API key not configured")

    prereqs_text = "\n".join(
        f"- {p.get('skillName', p.get('skill_name', '?'))}: "
        f"{p.get('confidenceLevel', p.get('confidence_level', '?'))}"
        for p in request.prerequisites
    ) if request.prerequisites else "None provided"

    prompt = f"""Generate 6-10 skill assessment questions for a student learning "{request.goal_title}".

STUDENT PROFILE:
- Education level: {request.education_level}
- Self-reported skills: {prereqs_text}

For each question, identify a prerequisite SKILL AREA that matters for this
learning goal. The student will rate their comfort level with each skill
(none / beginner / intermediate / advanced).

Focus on foundational knowledge areas the student needs. For example, for
"Binary Search", relevant skills would be: arrays/lists, sorting, loops,
conditionals, algorithm complexity, recursion, etc.

Each question should:
- Name a specific skill/concept (not a vague topic)
- Include "context" explaining WHY this skill matters for their goal

Return ONLY valid JSON:
{{"questions": [{{"id": "q1", "question": "Arrays and indexing", "context": "Binary search operates on sorted arrays, so you need to understand how array indices work."}}]}}"""

    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {groq_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": "openai/gpt-oss-120b",
                "messages": [
                    {"role": "system", "content": "You generate skill assessment questions. Return ONLY valid JSON."},
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.3,
                "max_tokens": 2000,
                "response_format": {"type": "json_object"},
            },
        )

    if resp.status_code != 200:
        raise HTTPException(status_code=502, detail=f"Groq error: {resp.text[:200]}")

    content = resp.json()["choices"][0]["message"]["content"]
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        raise HTTPException(status_code=500, detail="Failed to parse assessment questions")


@router.get("/status/{goal_id}", response_model=AgentStatusResponse)
async def get_research_status(
    goal_id: str,
    user: dict = Depends(get_current_user),
):
    """Get the current status of the research agent for a goal."""
    user_id = user["sub"]

    task = await get_agent_task(goal_id, "research")

    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Research task not found for this goal",
        )

    if task.get("user_id") != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to view this task",
        )

    return AgentStatusResponse(
        goal_id=goal_id,
        agent_type="research",
        status=task["status"],
        progress_percentage=task["progress_percentage"],
        current_task=task.get("current_task"),
        error_message=task.get("error_message"),
    )
