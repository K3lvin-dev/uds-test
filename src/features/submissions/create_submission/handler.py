import json
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from src.features.submissions.create_submission.schemas import (
    CreateSubmissionRequest,
    CreateSubmissionResponse,
)
from src.platform import s3
from src.platform.models import OutboxEvent, Submission


async def create_submission(
    request: CreateSubmissionRequest,
    db: AsyncSession,
) -> CreateSubmissionResponse:
    submission_id = uuid.uuid4()
    s3_key = f"submissions/{submission_id}.txt"

    await s3.upload_text(s3_key, request.text)

    submission = Submission(
        id=submission_id,
        student_id=request.student_id,
        s3_key=s3_key,
        status="PENDING",
    )
    outbox_event = OutboxEvent(
        aggregate_id=str(submission_id),
        topic="submissions-queue",
        payload=json.loads(json.dumps({"submission_id": str(submission_id)})),
        status="PENDING",
    )

    db.add(submission)
    db.add(outbox_event)
    await db.commit()
    await db.refresh(submission)

    return CreateSubmissionResponse.model_validate(submission)
