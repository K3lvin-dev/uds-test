import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel


class SubmissionDetailResponse(BaseModel):
    id: uuid.UUID
    student_id: str
    s3_key: str
    status: str
    score: Decimal | None
    criteria: dict[str, Any] | None
    overall_feedback: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
