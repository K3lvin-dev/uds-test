import json

import boto3
from botocore.client import BaseClient

from src.platform.config import settings


_sqs_client: BaseClient | None = None


def _client() -> BaseClient:
    global _sqs_client
    if _sqs_client is None:
        _sqs_client = boto3.client(
            "sqs",
            endpoint_url=settings.aws_endpoint_url,
            region_name=settings.aws_default_region,
            aws_access_key_id=settings.aws_access_key_id,
            aws_secret_access_key=settings.aws_secret_access_key,
        )
    return _sqs_client


def publish_message(submission_id: str) -> None:
    _client().send_message(
        QueueUrl=settings.sqs_queue_url,
        MessageBody=json.dumps({"submission_id": submission_id}),
    )


def receive_messages(
    max_messages: int = 1,
    visibility_timeout: int = 120,
    wait_seconds: int = 20,
) -> list[dict]:
    response = _client().receive_message(
        QueueUrl=settings.sqs_queue_url,
        MaxNumberOfMessages=max_messages,
        WaitTimeSeconds=wait_seconds,
        VisibilityTimeout=visibility_timeout,
    )
    return response.get("Messages", [])


def delete_message(receipt_handle: str) -> None:
    _client().delete_message(
        QueueUrl=settings.sqs_queue_url,
        ReceiptHandle=receipt_handle,
    )
