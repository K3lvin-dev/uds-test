from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from src.features.submissions.list_submissions.handler import list_submissions
from src.features.submissions.list_submissions.schemas import ListSubmissionsResponse
from src.infra.database import get_db


def setup(router: APIRouter) -> None:
    @router.get("/", response_model=ListSubmissionsResponse)
    async def list_submissions_endpoint(
        student_id: str = Query(..., description="ID do aluno"),
        page: int = Query(default=1, ge=1),
        per_page: int = Query(default=10, ge=1, le=100),
        db: AsyncSession = Depends(get_db),
    ) -> ListSubmissionsResponse:
        return await list_submissions(student_id, page, per_page, db)
