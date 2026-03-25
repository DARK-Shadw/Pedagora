from pydantic import BaseModel


class ResearchRequest(BaseModel):
    goal_id: str


class CoursePlanRequest(BaseModel):
    goal_id: str


class AnimateLessonRequest(BaseModel):
    goal_id: str
    lesson_id: str


class ProcessResourcesRequest(BaseModel):
    goal_id: str
