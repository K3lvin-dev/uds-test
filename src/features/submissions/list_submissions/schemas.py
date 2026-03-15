import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel

from src.infra.models import SubmissionStatus


class SubmissionSummary(BaseModel):
    id: uuid.UUID
    student_id: str
    status: SubmissionStatus
    score: Decimal | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ListSubmissionsResponse(BaseModel):
    items: list[SubmissionSummary]
    total: int
    page: int
    per_page: int
