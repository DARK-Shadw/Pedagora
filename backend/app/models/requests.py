from pydantic import BaseModel


class ResearchRequest(BaseModel):
    goal_id: str


class ProcessResourcesRequest(BaseModel):
    goal_id: str
