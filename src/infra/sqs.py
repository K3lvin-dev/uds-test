import asyncio
import json

import boto3
from botocore.config import Config

from src.infra.config import settings

_BOTO_CONFIG = Config(connect_timeout=5, read_timeout=30)


def _make_client():
    return boto3.session.Session().client(
        "sqs",
        endpoint_url=settings.aws_endpoint_url,
        region_name=settings.aws_default_region,
        aws_access_key_id=settings.aws_access_key_id,
        aws_secret_access_key=settings.aws_secret_access_key,
        config=_BOTO_CONFIG,
    )


def _publish_message_sync(submission_id: str) -> None:
    _make_client().send_message(
        QueueUrl=settings.sqs_queue_url,
        MessageBody=json.dumps({"submission_id": submission_id}),
    )


async def publish_message(submission_id: str) -> None:
    await asyncio.to_thread(_publish_message_sync, submission_id)


def _receive_messages_sync(
    max_messages: int = 1,
    visibility_timeout: int = 120,
    wait_seconds: int = 20,
) -> list[dict]:
    response = _make_client().receive_message(
        QueueUrl=settings.sqs_queue_url,
        MaxNumberOfMessages=max_messages,
        WaitTimeSeconds=wait_seconds,
        VisibilityTimeout=visibility_timeout,
    )
    return response.get("Messages", [])


async def receive_messages(
    max_messages: int = 1,
    visibility_timeout: int = 120,
    wait_seconds: int = 20,
) -> list[dict]:
    return await asyncio.to_thread(
        _receive_messages_sync, max_messages, visibility_timeout, wait_seconds
    )


def _delete_message_sync(receipt_handle: str) -> None:
    _make_client().delete_message(
        QueueUrl=settings.sqs_queue_url,
        ReceiptHandle=receipt_handle,
    )


async def delete_message(receipt_handle: str) -> None:
    await asyncio.to_thread(_delete_message_sync, receipt_handle)
