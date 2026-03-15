import asyncio

from sqlalchemy import cast, delete, select, update
from sqlalchemy.dialects.postgresql import UUID as PgUUID

from src.platform import s3, sqs
from src.platform.database import async_session_factory
from src.platform.models import OutboxEvent, Submission

_POLL_INTERVAL = 5


async def _relay_loop() -> None:
    print("[outbox_relay] Started. Polling outbox...")
    while True:
        try:
            async with async_session_factory() as db:
                result = await db.execute(
                    select(OutboxEvent, Submission)
                    .join(
                        Submission,
                        Submission.id
                        == cast(OutboxEvent.aggregate_id, PgUUID(as_uuid=True)),
                    )
                    .with_for_update(skip_locked=True)
                )
                rows = result.all()

                for event, submission in rows:
                    try:
                        await s3.upload_text(submission.s3_key, submission.raw_text)
                        await sqs.publish_message(str(submission.id))
                        await db.execute(
                            update(Submission)
                            .where(Submission.id == submission.id)
                            .values(raw_text=None)
                        )
                        await db.execute(
                            delete(OutboxEvent).where(OutboxEvent.id == event.id)
                        )
                        await db.commit()
                        print(f"[outbox_relay] event {event.id} -> deleted")
                    except Exception as exc:
                        await db.rollback()
                        print(
                            f"[outbox_relay] WARNING: falha ao processar evento {event.id}: {exc}"
                        )

        except Exception as exc:
            print(f"[outbox_relay] ERROR: falha ao acessar outbox: {exc}")

        await asyncio.sleep(_POLL_INTERVAL)


def main() -> None:
    asyncio.run(_relay_loop())


if __name__ == "__main__":
    main()
