import uuid

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.features.submissions.get_submission.schemas import SubmissionDetailResponse
from src.infra.models import Submission


async def get_submission(
    submission_id: uuid.UUID,
    db: AsyncSession,
) -> SubmissionDetailResponse:
    result = await db.execute(select(Submission).where(Submission.id == submission_id))
    submission = result.scalar_one_or_none()

    if not submission:
        raise HTTPException(status_code=404, detail="Submission not found")

    return SubmissionDetailResponse.model_validate(submission)
