import asyncio
from typing import Any

from mypy_boto3_sqs.type_defs import MessageTypeDef

from src.infra import sqs
from src.workers.grade_submission.handler import process

# --- modo local: daemon com polling SQS ---


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
                await sqs.delete_message(receipt_handle)
            except Exception as exc:
                print(f"[grade_worker] WARNING: falha ao processar mensagem: {exc}")


def main() -> None:
    try:
        asyncio.run(_poll_loop())
    except (KeyboardInterrupt, asyncio.exceptions.CancelledError):
        print("[grade_worker] Stopped.")


# --- modo AWS Lambda: acionado pelo SQS Event Source Mapping ---


async def _process_records(records: list[MessageTypeDef]) -> None:
    for record in records:
        await process(record)


def lambda_handler(event: dict[str, Any], context: Any) -> None:
    """Entry point para AWS Lambda com SQS Event Source Mapping.

    A AWS entrega as mensagens prontas em event["Records"] —
    sem polling, sem loop. Processa e retorna.

    Os records do Lambda usam camelCase (body, receiptHandle), enquanto
    process() espera o formato boto3 (Body, ReceiptHandle). A normalização
    abaixo garante compatibilidade entre os dois formatos.
    """
    records: list[MessageTypeDef] = [
        {"Body": r["body"], "ReceiptHandle": r["receiptHandle"]}
        for r in event["Records"]
    ]
    asyncio.run(_process_records(records))


if __name__ == "__main__":
    main()
