from pydantic import BaseModel, Field


class CriterionResult(BaseModel):
    score: float = Field(ge=0, le=10)
    feedback: str


class GradingResult(BaseModel):
    score: float = Field(ge=0, le=10)
    criteria: dict[str, CriterionResult]
    overall_feedback: str
