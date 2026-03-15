import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel

from src.infra.models import SubmissionStatus
from src.workers.grade_submission.schemas import CriterionResult


class SubmissionDetailResponse(BaseModel):
    id: uuid.UUID
    student_id: str
    s3_key: str
    status: SubmissionStatus
    score: Decimal | None
    criteria: dict[str, CriterionResult] | None
    overall_feedback: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
