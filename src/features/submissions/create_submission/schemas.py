import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from src.infra.models import SubmissionStatus


class CreateSubmissionRequest(BaseModel):
    student_id: str = Field(min_length=1, max_length=100)
    text: str = Field(min_length=1, max_length=10_000)


class CreateSubmissionResponse(BaseModel):
    id: uuid.UUID
    student_id: str
    status: SubmissionStatus
    created_at: datetime

    model_config = {"from_attributes": True}
