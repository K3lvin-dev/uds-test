import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel


class SubmissionSummary(BaseModel):
    id: uuid.UUID
    student_id: str
    status: str
    score: Decimal | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ListSubmissionsResponse(BaseModel):
    items: list[SubmissionSummary]
    total: int
    page: int
    per_page: int
