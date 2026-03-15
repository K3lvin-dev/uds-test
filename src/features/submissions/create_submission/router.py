from fastapi import APIRouter, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession

from src.features.submissions.create_submission.handler import create_submission
from src.features.submissions.create_submission.schemas import (
    CreateSubmissionRequest,
    CreateSubmissionResponse,
)
from src.infra.database import get_db


def setup(router: APIRouter) -> None:
    @router.post("/", response_model=CreateSubmissionResponse, status_code=201)
    async def create_submission_endpoint(
        request: CreateSubmissionRequest,
        response: Response,
        db: AsyncSession = Depends(get_db),
    ) -> CreateSubmissionResponse:
        result = await create_submission(request, db)
        response.headers["Location"] = f"/api/v1/submissions/{result.id}"
        return result
