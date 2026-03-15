import uuid
from decimal import Decimal

from pydantic import BaseModel

from src.infra.models import SubmissionStatus
from src.infra.types import BRTDatetime
from src.workers.grade_submission.schemas import CriterionResult


class SubmissionDetailResponse(BaseModel):
    id: uuid.UUID
    student_id: str
    s3_key: str
    status: SubmissionStatus
    score: Decimal | None
    criteria: dict[str, CriterionResult] | None
    overall_feedback: str | None
    created_at: BRTDatetime
    updated_at: BRTDatetime

    model_config = {"from_attributes": True}
