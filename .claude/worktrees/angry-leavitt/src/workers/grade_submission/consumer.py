import asyncio

from src.infra import sqs
from src.workers.grade_submission.handler import process


async def _poll_loop() -> None:
    print("[grade_worker] Started. Polling SQS...")
    while True:
        messages = await sqs.receive_messages(
            max_messages=1,
            visibility_timeout=120,
            wait_seconds=20,
        )

        for message in messages:
            receipt_handle = message.get("ReceiptHandle")
            if not receipt_handle:
                continue

            try:
                await process(message)
            except Exception as exc:
                print(f"[grade_worker] WARNING: falha ao processar mensagem: {exc}")
            finally:
                await sqs.delete_message(receipt_handle)


def main() -> None:
    try:
        asyncio.run(_poll_loop())
    except (KeyboardInterrupt, asyncio.exceptions.CancelledError):
        print("[grade_worker] Stopped.")


if __name__ == "__main__":
    main()
