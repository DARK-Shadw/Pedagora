from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status

from app.auth.dependencies import get_current_user
from app.models.requests import ResearchRequest
from app.models.responses import ResearchAccepted, AgentStatusResponse
from app.services.agent_task import get_agent_task, update_agent_task, cleanup_previous_research
from app.agents.pipeline import run_research_pipeline

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
    background_tasks.add_task(run_research_pipeline, goal_id, user_id)

    return ResearchAccepted(goal_id=goal_id, task_id=task["id"])


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
