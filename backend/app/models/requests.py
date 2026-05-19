from pydantic import BaseModel


class CoursePlanRequest(BaseModel):
    goal_id: str


class AnimateLessonRequest(BaseModel):
    goal_id: str
    lesson_id: str


class RegenerateFrameRequest(BaseModel):
    goal_id: str
    lesson_id: str
    frame_id: str
