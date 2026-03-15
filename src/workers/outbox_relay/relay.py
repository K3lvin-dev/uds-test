import asyncio

from sqlalchemy import delete, select

from src.infra import s3, sqs
from src.infra.database import async_session_factory
from src.infra.models import OutboxEvent

_POLL_INTERVAL = 5


async def _relay_loop() -> None:
    print("[outbox_relay] Started. Polling outbox...")
    while True:
        try:
            async with async_session_factory() as db:
                result = await db.execute(
                    select(OutboxEvent).with_for_update(skip_locked=True)
                )
                events = result.scalars().all()

                for event in events:
                    try:
                        submission_id = event.payload["submission_id"]
                        text = event.payload["text"]
                        s3_key = f"submissions/{submission_id}.txt"

                        await s3.upload_text(s3_key, text)
                        await sqs.publish_message(submission_id)
                        await db.execute(
                            delete(OutboxEvent).where(OutboxEvent.id == event.id)
                        )
                        await db.commit()
                        print(f"[outbox_relay] event {event.id} -> processed")
                    except Exception as exc:
                        await db.rollback()
                        print(
                            f"[outbox_relay] WARNING: falha ao processar evento {event.id}: {exc}"
                        )

        except Exception as exc:
            print(f"[outbox_relay] ERROR: falha ao acessar outbox: {exc}")

        await asyncio.sleep(_POLL_INTERVAL)


def main() -> None:
    try:
        asyncio.run(_relay_loop())
    except (KeyboardInterrupt, asyncio.exceptions.CancelledError):
        print("[outbox_relay] Stopped.")


if __name__ == "__main__":
    main()
