import asyncio
import json

from sqlalchemy import select, update

from src.platform import sqs
from src.platform.database import async_session_factory
from src.platform.models import OutboxEvent

_POLL_INTERVAL = 5


async def _relay_loop() -> None:
    print("[outbox_relay] Started. Polling outbox...")
    while True:
        try:
            async with async_session_factory() as db:
                result = await db.execute(
                    select(OutboxEvent).where(OutboxEvent.status == "PENDING")
                )
                events = result.scalars().all()

                for event in events:
                    try:
                        await sqs.publish_message(json.dumps(event.payload))
                        await db.execute(
                            update(OutboxEvent)
                            .where(OutboxEvent.id == event.id)
                            .values(status="PROCESSED")
                        )
                        await db.commit()
                        print(f"[outbox_relay] event {event.id} -> PROCESSED")
                    except Exception as exc:
                        print(
                            f"[outbox_relay] WARNING: falha ao publicar evento {event.id}: {exc}"  # noqa: E501
                        )

        except Exception as exc:
            print(f"[outbox_relay] ERROR: falha ao acessar outbox: {exc}")

        await asyncio.sleep(_POLL_INTERVAL)


def main() -> None:
    asyncio.run(_relay_loop())


if __name__ == "__main__":
    main()
