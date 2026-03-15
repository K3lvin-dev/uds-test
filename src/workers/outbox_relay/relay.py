import asyncio
from datetime import UTC, datetime, timedelta
from typing import TypedDict, cast

from sqlalchemy import delete, select, update

from src.infra import s3, sqs
from src.infra.database import async_session_factory
from src.infra.models import OutboxEvent, Submission, SubmissionStatus


class OutboxPayload(TypedDict):
    submission_id: str
    text: str


_POLL_INTERVAL = 5
_MAX_RETRIES = 3
_RETRY_AFTER_MINUTES = 5


async def _process_one() -> bool:
    async with async_session_factory() as db:
        result = await db.execute(
            select(OutboxEvent).with_for_update(skip_locked=True).limit(1)
        )
        event = result.scalar_one_or_none()

        if event is None:
            return False

        payload = cast(OutboxPayload, event.payload)
        submission_id = payload["submission_id"]
        text = payload["text"]
        s3_key = f"submissions/{submission_id}.txt"

        await s3.upload_text(s3_key, text)
        await sqs.publish_message(submission_id)
        await db.execute(delete(OutboxEvent).where(OutboxEvent.id == event.id))
        await db.commit()
        print(f"[outbox_relay] event {event.id} -> processed")
        return True


async def _retry_errors() -> None:
    retry_threshold = datetime.now(UTC) - timedelta(minutes=_RETRY_AFTER_MINUTES)

    async with async_session_factory() as db:
        result = await db.execute(
            select(Submission)
            .where(
                Submission.status == SubmissionStatus.ERROR,
                Submission.retry_count < _MAX_RETRIES,
                Submission.updated_at < retry_threshold,
            )
            .with_for_update(skip_locked=True)
        )
        submissions = result.scalars().all()

        for submission in submissions:
            await sqs.publish_message(str(submission.id))
            await db.execute(
                update(Submission)
                .where(Submission.id == submission.id)
                .values(
                    status=SubmissionStatus.PENDING,
                    retry_count=submission.retry_count + 1,
                    updated_at=datetime.now(UTC),
                )
            )
            await db.commit()
            print(
                f"[outbox_relay] submission {submission.id} -> retry "
                f"{submission.retry_count + 1}/{_MAX_RETRIES}"
            )


async def _relay_loop() -> None:
    print("[outbox_relay] Started. Polling outbox...")
    while True:
        try:
            has_more = await _process_one()
            if not has_more:
                await _retry_errors()
                await asyncio.sleep(_POLL_INTERVAL)
        except Exception as exc:
            print(f"[outbox_relay] WARNING: {exc}")
            await asyncio.sleep(_POLL_INTERVAL)


def main() -> None:
    try:
        asyncio.run(_relay_loop())
    except (KeyboardInterrupt, asyncio.exceptions.CancelledError):
        print("[outbox_relay] Stopped.")


if __name__ == "__main__":
    main()
