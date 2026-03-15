import asyncio
from typing import TYPE_CHECKING

import boto3
from botocore.config import Config

from src.infra.config import settings

if TYPE_CHECKING:
    from mypy_boto3_s3 import S3Client
else:
    S3Client = object

_BOTO_CONFIG = Config(connect_timeout=5, read_timeout=30)


def _make_client() -> S3Client:
    return boto3.Session().client(
        "s3",
        endpoint_url=settings.aws_endpoint_url,
        region_name=settings.aws_default_region,
        aws_access_key_id=settings.aws_access_key_id,
        aws_secret_access_key=settings.aws_secret_access_key,
        config=_BOTO_CONFIG,
    )


def _upload_text_sync(s3_key: str, text: str) -> None:
    _make_client().put_object(
        Bucket=settings.s3_bucket,
        Key=s3_key,
        Body=text.encode("utf-8"),
        ContentType="text/plain; charset=utf-8",
    )


async def upload_text(s3_key: str, text: str) -> None:
    await asyncio.to_thread(_upload_text_sync, s3_key, text)


def _download_text_sync(s3_key: str) -> str:
    response = _make_client().get_object(Bucket=settings.s3_bucket, Key=s3_key)
    return response["Body"].read().decode("utf-8")


async def download_text(s3_key: str) -> str:
    return await asyncio.to_thread(_download_text_sync, s3_key)
