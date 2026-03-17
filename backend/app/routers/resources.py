"""Resource processing endpoints: trigger processing, check status."""

import logging

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status

from app.auth.dependencies import get_current_user
from app.models.requests import ProcessResourcesRequest
from app.services.supabase import get_supabase

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/process", status_code=status.HTTP_202_ACCEPTED)
async def trigger_processing(
    request: ProcessResourcesRequest,
    background_tasks: BackgroundTasks,
    user: dict = Depends(get_current_user),
):
    """Trigger resource processing pipeline for a goal. Returns 202 immediately."""
    user_id = user["sub"]
    goal_id = request.goal_id
    sb = get_supabase()

    # Verify resources exist for this goal and belong to user
    result = (
        sb.table("user_resources")
        .select("id, status")
        .eq("goal_id", goal_id)
        .eq("user_id", user_id)
        .eq("status", "uploaded")
        .execute()
    )

    if not result.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No uploaded resources found for this goal",
        )

    # Mark all as processing
    for resource in result.data:
        sb.table("user_resources").update({"status": "processing"}).eq(
            "id", resource["id"]
        ).execute()

    # Import here to avoid circular imports
    from app.resources.pipeline import run_resource_pipeline

    background_tasks.add_task(run_resource_pipeline, goal_id, user_id)

    return {"message": "Resource processing started", "goal_id": goal_id, "resource_count": len(result.data)}


@router.get("/status/{goal_id}")
async def get_processing_status(
    goal_id: str,
    user: dict = Depends(get_current_user),
):
    """Get processing status for all resources of a goal."""
    user_id = user["sub"]
    sb = get_supabase()

    result = (
        sb.table("user_resources")
        .select("id, file_name, status, error_message, chunk_count, figure_count")
        .eq("goal_id", goal_id)
        .eq("user_id", user_id)
        .execute()
    )

    if not result.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No resources found for this goal",
        )

    return {"goal_id": goal_id, "resources": result.data}
