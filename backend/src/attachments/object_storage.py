"""Replit Object Storage integration for file uploads.

Uses the Replit sidecar API at 127.0.0.1:1106 to get signed URLs
for Google Cloud Storage operations.
"""

import os
import uuid
import logging
from datetime import datetime, timezone, timedelta

import httpx

logger = logging.getLogger(__name__)

REPLIT_SIDECAR_ENDPOINT = "http://127.0.0.1:1106"


def _get_bucket_id() -> str:
    val = os.environ.get("DEFAULT_OBJECT_STORAGE_BUCKET_ID", "")
    if not val:
        raise RuntimeError("DEFAULT_OBJECT_STORAGE_BUCKET_ID is not set")
    return val


def _get_private_dir() -> str:
    val = os.environ.get("PRIVATE_OBJECT_DIR", "")
    if not val:
        raise RuntimeError("PRIVATE_OBJECT_DIR is not set")
    return val


def _parse_object_path(path: str) -> tuple[str, str]:
    if not path.startswith("/"):
        path = f"/{path}"
    parts = path.split("/")
    if len(parts) < 3:
        raise ValueError("Invalid path: must contain at least a bucket name")
    bucket_name = parts[1]
    object_name = "/".join(parts[2:])
    return bucket_name, object_name


async def _sign_url(
    bucket_name: str,
    object_name: str,
    method: str = "PUT",
    ttl_sec: int = 900,
) -> str:
    expires_at = (datetime.now(timezone.utc) + timedelta(seconds=ttl_sec)).isoformat()
    payload = {
        "bucket_name": bucket_name,
        "object_name": object_name,
        "method": method,
        "expires_at": expires_at,
    }
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{REPLIT_SIDECAR_ENDPOINT}/object-storage/signed-object-url",
            json=payload,
            timeout=15.0,
        )
        resp.raise_for_status()
        data = resp.json()
        return data["signed_url"]


def generate_object_key(entity_type: str, entity_id: int, extension: str) -> str:
    unique = uuid.uuid4().hex
    return f"uploads/{entity_type}/{entity_id}/{unique}.{extension}"


async def get_upload_url(object_key: str) -> str:
    private_dir = _get_private_dir()
    full_path = f"{private_dir}/{object_key}"
    bucket_name, object_name = _parse_object_path(full_path)
    return await _sign_url(bucket_name, object_name, method="PUT", ttl_sec=900)


async def get_download_url(object_key: str, ttl_sec: int = 3600) -> str:
    private_dir = _get_private_dir()
    full_path = f"{private_dir}/{object_key}"
    bucket_name, object_name = _parse_object_path(full_path)
    return await _sign_url(bucket_name, object_name, method="GET", ttl_sec=ttl_sec)


async def upload_file_bytes(
    content: bytes,
    object_key: str,
    content_type: str = "application/octet-stream",
) -> str:
    upload_url = await get_upload_url(object_key)
    async with httpx.AsyncClient() as client:
        resp = await client.put(
            upload_url,
            content=content,
            headers={"Content-Type": content_type},
            timeout=60.0,
        )
        resp.raise_for_status()
    return object_key


async def delete_object(object_key: str) -> None:
    private_dir = _get_private_dir()
    full_path = f"{private_dir}/{object_key}"
    bucket_name, object_name = _parse_object_path(full_path)
    try:
        delete_url = await _sign_url(bucket_name, object_name, method="DELETE", ttl_sec=60)
        async with httpx.AsyncClient() as client:
            await client.delete(delete_url, timeout=15.0)
    except Exception as e:
        logger.warning("Failed to delete object %s: %s", object_key, e)


def is_object_storage_available() -> bool:
    return bool(
        os.environ.get("DEFAULT_OBJECT_STORAGE_BUCKET_ID")
        and os.environ.get("PRIVATE_OBJECT_DIR")
    )
