import asyncio

from sqlalchemy import delete, select

from src.infra import s3, sqs
from src.infra.database import async_session_factory
from src.infra.models import OutboxEvent

_POLL_INTERVAL = 5


async def _process_one() -> bool:
    async with async_session_factory() as db:
        result = await db.execute(
            select(OutboxEvent)
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        event = result.scalar_one_or_none()

        if event is None:
            return False

        submission_id = event.payload["submission_id"]
        text = event.payload["text"]
        s3_key = f"submissions/{submission_id}.txt"

        await s3.upload_text(s3_key, text)
        await sqs.publish_message(submission_id)
        await db.execute(delete(OutboxEvent).where(OutboxEvent.id == event.id))
        await db.commit()
        print(f"[outbox_relay] event {event.id} -> processed")
        return True


async def _relay_loop() -> None:
    print("[outbox_relay] Started. Polling outbox...")
    while True:
        try:
            has_more = await _process_one()
            if not has_more:
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
