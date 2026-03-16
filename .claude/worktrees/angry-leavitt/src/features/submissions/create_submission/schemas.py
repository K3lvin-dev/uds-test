import uuid

from pydantic import BaseModel, Field

from src.infra.models import SubmissionStatus
from src.infra.types import BRTDatetime


class CreateSubmissionRequest(BaseModel):
    student_id: str = Field(min_length=1, max_length=100)
    text: str = Field(min_length=1, max_length=10_000)


class CreateSubmissionResponse(BaseModel):
    id: uuid.UUID
    student_id: str
    status: SubmissionStatus
    created_at: BRTDatetime

    model_config = {"from_attributes": True}
