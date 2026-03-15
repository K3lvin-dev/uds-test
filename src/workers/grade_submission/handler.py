import asyncio
import json
import uuid
from datetime import datetime, timezone

from sqlalchemy import select, update

from src.infra import s3
from src.infra.database import async_session_factory
from src.infra.models import Submission
from src.workers.grade_submission.grader import grade


async def process(message: dict) -> None:
    body = json.loads(message["Body"])
    submission_id = uuid.UUID(body["submission_id"])

    async with async_session_factory() as db:
        result = await db.execute(
            select(Submission)
            .where(Submission.id == submission_id)
            .with_for_update()
        )
        submission = result.scalar_one_or_none()

        if not submission:
            return

        if submission.status != "PENDING":
            return

        await db.execute(
            update(Submission)
            .where(Submission.id == submission_id)
            .values(status="PROCESSING", updated_at=datetime.now(timezone.utc))
        )
        await db.commit()

        try:
            text = await s3.download_text(submission.s3_key)
            grading = await asyncio.to_thread(grade, text)

            await db.execute(
                update(Submission)
                .where(Submission.id == submission_id)
                .values(
                    status="GRADED",
                    score=grading.score,
                    criteria={k: v.model_dump() for k, v in grading.criteria.items()},
                    overall_feedback=grading.overall_feedback,
                    updated_at=datetime.now(timezone.utc),
                )
            )
            await db.commit()
            print(f"[grade_worker] submission {submission_id} graded — score: {grading.score}")

        except Exception as exc:
            print(f"[grade_worker] ERROR grading {submission_id}: {exc}")
            await db.execute(
                update(Submission)
                .where(Submission.id == submission_id)
                .values(status="ERROR", updated_at=datetime.now(timezone.utc))
            )
            await db.commit()
