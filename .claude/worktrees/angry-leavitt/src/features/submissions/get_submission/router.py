import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.features.submissions.get_submission.handler import get_submission
from src.features.submissions.get_submission.schemas import SubmissionDetailResponse
from src.infra.database import get_db


def setup(router: APIRouter) -> None:
    @router.get("/{submission_id}", response_model=SubmissionDetailResponse)
    async def get_submission_endpoint(
        submission_id: uuid.UUID,
        db: AsyncSession = Depends(get_db),
    ) -> SubmissionDetailResponse:
        return await get_submission(submission_id, db)
