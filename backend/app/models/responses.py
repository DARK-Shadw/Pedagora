from pydantic import BaseModel


class ResearchAccepted(BaseModel):
    message: str = "Research pipeline started"
    goal_id: str
    task_id: str


class CoursePlanAccepted(BaseModel):
    message: str = "Course planner pipeline started"
    goal_id: str
    task_id: str


class AnimateLessonAccepted(BaseModel):
    message: str = "Animation pipeline started"
    goal_id: str
    lesson_id: str


class RegenerateFrameAccepted(BaseModel):
    message: str = "Frame regeneration started"
    goal_id: str
    lesson_id: str
    frame_id: str


class AgentStatusResponse(BaseModel):
    goal_id: str
    agent_type: str
    status: str
    progress_percentage: float
    current_task: str | None
    error_message: str | None
