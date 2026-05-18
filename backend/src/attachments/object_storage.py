"""Cloudflare R2 object storage integration for file uploads.

Uses S3-compatible API via boto3 to interact with Cloudflare R2 buckets.
"""

import logging
import os
import uuid
from asyncio import to_thread
from collections.abc import Callable
from typing import TypeVar

import boto3
from botocore.config import Config as BotoConfig

logger = logging.getLogger(__name__)
T = TypeVar("T")


async def _run_boto(call: Callable[[], T]) -> T:
    """Run boto3's blocking client work off the async event loop."""
    return await to_thread(call)


def _get_r2_client():
    account_id = os.environ.get("R2_ACCOUNT_ID", "")
    access_key = os.environ.get("R2_ACCESS_KEY_ID", "")
    secret_key = os.environ.get("R2_SECRET_ACCESS_KEY", "")
    if not all([account_id, access_key, secret_key]):
        raise RuntimeError("R2 credentials not configured (R2_ACCOUNT_ID, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY)")

    return boto3.client(
        "s3",
        endpoint_url=f"https://{account_id}.r2.cloudflarestorage.com",
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        config=BotoConfig(signature_version="s3v4"),
        region_name="auto",
    )


def _get_bucket_name() -> str:
    return os.environ.get("R2_BUCKET_NAME", "crm-app")


def generate_object_key(entity_type: str, entity_id: int, extension: str) -> str:
    unique = uuid.uuid4().hex
    return f"uploads/{entity_type}/{entity_id}/{unique}.{extension}"


async def get_upload_url(object_key: str) -> str:
    client = _get_r2_client()
    return await _run_boto(
        lambda: client.generate_presigned_url(
            "put_object",
            Params={"Bucket": _get_bucket_name(), "Key": object_key},
            ExpiresIn=900,
        )
    )


async def get_download_url(object_key: str, ttl_sec: int = 3600) -> str:
    client = _get_r2_client()
    return await _run_boto(
        lambda: client.generate_presigned_url(
            "get_object",
            Params={"Bucket": _get_bucket_name(), "Key": object_key},
            ExpiresIn=ttl_sec,
        )
    )


async def download_object_bytes(object_key: str) -> bytes:
    """Fetch the raw bytes of an R2 object via boto3.

    Used for server-side reads that need the file in-process (PDF
    stamping, signature replay) rather than a presigned URL handed
    to a browser. Surfaces the boto error directly so the caller can
    distinguish missing-object from credential errors.
    """
    client = _get_r2_client()

    def _download() -> bytes:
        response = client.get_object(Bucket=_get_bucket_name(), Key=object_key)
        return response["Body"].read()

    return await _run_boto(_download)


async def upload_file_bytes(
    content: bytes,
    object_key: str,
    content_type: str = "application/octet-stream",
) -> str:
    client = _get_r2_client()
    await _run_boto(
        lambda: client.put_object(
            Bucket=_get_bucket_name(),
            Key=object_key,
            Body=content,
            ContentType=content_type,
        )
    )
    return object_key


async def delete_object(object_key: str) -> None:
    try:
        client = _get_r2_client()
        await _run_boto(
            lambda: client.delete_object(Bucket=_get_bucket_name(), Key=object_key)
        )
    except Exception as e:
        logger.warning("Failed to delete object %s: %s", object_key, e)


def is_object_storage_available() -> bool:
    return bool(
        os.environ.get("R2_ACCOUNT_ID")
        and os.environ.get("R2_ACCESS_KEY_ID")
        and os.environ.get("R2_SECRET_ACCESS_KEY")
    )
