from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.features.submissions.list_submissions.schemas import (
    ListSubmissionsResponse,
    SubmissionSummary,
)
from src.infra.models import Submission


async def list_submissions(
    student_id: str,
    page: int,
    per_page: int,
    db: AsyncSession,
) -> ListSubmissionsResponse:
    offset = (page - 1) * per_page

    total = (
        await db.execute(
            select(func.count())
            .select_from(Submission)
            .where(Submission.student_id == student_id)
        )
    ).scalar_one()

    rows = (
        (
            await db.execute(
                select(Submission)
                .where(Submission.student_id == student_id)
                .order_by(Submission.created_at.desc())
                .offset(offset)
                .limit(per_page)
            )
        )
        .scalars()
        .all()
    )

    return ListSubmissionsResponse(
        items=[SubmissionSummary.model_validate(s) for s in rows],
        total=total,
        page=page,
        per_page=per_page,
    )
