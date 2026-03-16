import uuid
from decimal import Decimal

from pydantic import BaseModel

from src.infra.models import SubmissionStatus
from src.infra.types import BRTDatetime


class SubmissionSummary(BaseModel):
    id: uuid.UUID
    student_id: str
    status: SubmissionStatus
    score: Decimal | None
    created_at: BRTDatetime
    updated_at: BRTDatetime

    model_config = {"from_attributes": True}


class ListSubmissionsResponse(BaseModel):
    items: list[SubmissionSummary]
    total: int
    page: int
    per_page: int
