"""Cloudflare R2 object storage integration for file uploads.

Uses S3-compatible API via boto3 to interact with Cloudflare R2 buckets.
"""

import logging
import os
import uuid

import boto3
from botocore.config import Config as BotoConfig

logger = logging.getLogger(__name__)


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
    return client.generate_presigned_url(
        "put_object",
        Params={"Bucket": _get_bucket_name(), "Key": object_key},
        ExpiresIn=900,
    )


async def get_download_url(object_key: str, ttl_sec: int = 3600) -> str:
    client = _get_r2_client()
    return client.generate_presigned_url(
        "get_object",
        Params={"Bucket": _get_bucket_name(), "Key": object_key},
        ExpiresIn=ttl_sec,
    )


async def upload_file_bytes(
    content: bytes,
    object_key: str,
    content_type: str = "application/octet-stream",
) -> str:
    client = _get_r2_client()
    client.put_object(
        Bucket=_get_bucket_name(),
        Key=object_key,
        Body=content,
        ContentType=content_type,
    )
    return object_key


async def delete_object(object_key: str) -> None:
    try:
        client = _get_r2_client()
        client.delete_object(Bucket=_get_bucket_name(), Key=object_key)
    except Exception as e:
        logger.warning("Failed to delete object %s: %s", object_key, e)


def is_object_storage_available() -> bool:
    return bool(
        os.environ.get("R2_ACCOUNT_ID")
        and os.environ.get("R2_ACCESS_KEY_ID")
        and os.environ.get("R2_SECRET_ACCESS_KEY")
    )
