import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from src.features.submissions.create_submission.schemas import (
    CreateSubmissionRequest,
    CreateSubmissionResponse,
)
from src.infra import s3, sqs
from src.infra.models import Submission, SubmissionStatus


async def create_submission(
    request: CreateSubmissionRequest,
    db: AsyncSession,
) -> CreateSubmissionResponse:
    submission_id = uuid.uuid4()
    s3_key = f"submissions/{submission_id}.txt"

    submission = Submission(
        id=submission_id,
        student_id=request.student_id,
        s3_key=s3_key,
        status=SubmissionStatus.PENDING,
    )
    db.add(submission)
    await db.commit()
    await db.refresh(submission)

    try:
        await s3.upload_text(s3_key, request.text)
    except Exception:
        await db.delete(submission)
        await db.commit()
        raise

    await sqs.publish_message(str(submission_id))

    return CreateSubmissionResponse.model_validate(submission)
