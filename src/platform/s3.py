import asyncio

import boto3
from botocore.client import BaseClient

from src.platform.config import settings

_s3_client: BaseClient | None = None


def _client() -> BaseClient:
    global _s3_client
    if _s3_client is None:
        _s3_client = boto3.client(
            "s3",
            endpoint_url=settings.aws_endpoint_url,
            region_name=settings.aws_default_region,
            aws_access_key_id=settings.aws_access_key_id,
            aws_secret_access_key=settings.aws_secret_access_key,
        )
    return _s3_client


def _upload_text_sync(s3_key: str, text: str) -> None:
    _client().put_object(
        Bucket=settings.s3_bucket,
        Key=s3_key,
        Body=text.encode("utf-8"),
        ContentType="text/plain; charset=utf-8",
    )


async def upload_text(s3_key: str, text: str) -> None:
    await asyncio.to_thread(_upload_text_sync, s3_key, text)


def _download_text_sync(s3_key: str) -> str:
    response = _client().get_object(Bucket=settings.s3_bucket, Key=s3_key)
    return response["Body"].read().decode("utf-8")


async def download_text(s3_key: str) -> str:
    return await asyncio.to_thread(_download_text_sync, s3_key)
