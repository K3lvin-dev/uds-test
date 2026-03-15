from enum import StrEnum

from pydantic import BaseModel, Field


class GradingCriteria(StrEnum):
    GRAMMAR = "grammar"
    COHERENCE = "coherence"
    ARGUMENTATION = "argumentation"
    VOCABULARY = "vocabulary"


class CriterionResult(BaseModel):
    score: float = Field(ge=0, le=10)
    feedback: str


class GradingResult(BaseModel):
    score: float = Field(ge=0, le=10)
    criteria: dict[GradingCriteria, CriterionResult]
    overall_feedback: str
