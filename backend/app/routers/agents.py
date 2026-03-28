from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from pydantic import BaseModel

from app.auth.dependencies import get_current_user
from app.models.requests import ResearchRequest, CoursePlanRequest, AnimateLessonRequest
from app.models.responses import ResearchAccepted, CoursePlanAccepted, AnimateLessonAccepted, AgentStatusResponse
from app.services.agent_task import get_agent_task, update_agent_task, cleanup_previous_research, fetch_research_results, fetch_course_plan, get_lesson_animations
from app.agents.research_v3 import run_research_v3
from app.agents.course_planner.pipeline_v4 import run_course_planner_v4
from app.agents.animation.pipeline import run_animation_pipeline

router = APIRouter()


@router.post("/research", status_code=status.HTTP_202_ACCEPTED, response_model=ResearchAccepted)
async def trigger_research(
    request: ResearchRequest,
    background_tasks: BackgroundTasks,
    user: dict = Depends(get_current_user),
):
    """Trigger the research pipeline for a learning goal. Returns 202 immediately."""
    user_id = user["sub"]
    goal_id = request.goal_id

    # Verify the task exists, belongs to user, and is in a valid state
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

    # Reset task state for retries
    if task.get("status") == "failed":
        await update_agent_task(
            goal_id,
            "research",
            status="queued",
            progress=0,
            current_task=None,
            error_message=None,
            log_message="Task reset for retry",
            log_level="system",
        )

    # Launch pipeline in background
    background_tasks.add_task(run_research_v3, goal_id, user_id)

    return ResearchAccepted(goal_id=goal_id, task_id=task["id"])


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

    background_tasks.add_task(run_animation_pipeline, goal_id, user_id, lesson_id)
    return AnimateLessonAccepted(goal_id=goal_id, lesson_id=lesson_id)


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
    """Generate skill assessment questions using Claude Code."""
    from app.engine.claude_engine import ClaudeEngine
    engine = ClaudeEngine(model="haiku")

    prereqs_text = "\n".join(
        f"- {p.get('skillName', p.get('skill_name', '?'))}: "
        f"{p.get('confidenceLevel', p.get('confidence_level', '?'))}"
        for p in request.prerequisites
    ) if request.prerequisites else "None provided"

    result = await engine.run(
        prompt=f"""Generate 6-10 prerequisite assessment questions for a student.

STUDENT PROFILE:
- Education level: {request.education_level}
- Learning goal: {request.goal_title}
- Self-reported skills:
{prereqs_text}

Generate questions that PROBE whether the student truly understands the
prerequisites needed for this learning goal. Focus on foundational knowledge
that will be essential — don't ask surface-level questions.

For a goal like "video diffusion models", good questions would probe:
- Probability distributions and Bayes' theorem
- Neural network architectures (what is a U-Net?)
- Loss functions and optimization
- Basic linear algebra (matrix multiplication, eigenvalues)

Each question should have a "context" explaining WHY this knowledge matters
for the student's specific goal.

Return ONLY valid JSON (no markdown):
{{"questions": [{{"id": "q1", "question": "Can you explain...", "context": "This matters because..."}}]}}""",
        timeout=60,
    )

    import json
    try:
        return json.loads(result["result"])
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
