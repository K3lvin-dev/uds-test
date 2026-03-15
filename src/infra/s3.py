import asyncio

import boto3

from src.infra.config import settings


def _make_client():
    return boto3.session.Session().client(
        "s3",
        endpoint_url=settings.aws_endpoint_url,
        region_name=settings.aws_default_region,
        aws_access_key_id=settings.aws_access_key_id,
        aws_secret_access_key=settings.aws_secret_access_key,
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
