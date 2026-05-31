"""Storage abstraction for onboarding template PDFs (build-order §D).

Dispatches on ``_use_object_storage()`` (Cloudflare R2 vs local disk) so a
dev box with no R2 creds writes to ``uploads/onboarding/`` while production
writes to R2 — with zero config branching at the call sites. Onboarding-owned;
does not modify ``attachments/``.

Storage ref conventions (stored in ``OnboardingTemplate.pdf_path``):
  * R2  → ``"obj://<key>"``
  * disk → path relative to ``uploads/`` (mirrors AttachmentService)
"""

from pathlib import Path

from botocore.exceptions import ClientError

from src.attachments.object_storage import (
    delete_object,
    download_object_bytes,
    object_exists,
    upload_file_bytes,
)
from src.attachments.service import _use_object_storage

_OBJ_PREFIX = "obj://"

# ``uploads/onboarding`` — sibling of ``uploads/<entity_type>`` used by
# AttachmentService, so disk refs stay relative to the shared ``uploads/`` root.
ONBOARDING_DIR = Path(__file__).parent.parent.parent / "uploads" / "onboarding"
_UPLOADS_ROOT = ONBOARDING_DIR.parent


async def write(key: str, content: bytes, content_type: str = "application/pdf") -> str:
    """Persist ``content`` under ``key`` and return its storage ref."""
    if _use_object_storage():
        await upload_file_bytes(content, key, content_type)
        return f"{_OBJ_PREFIX}{key}"
    dest = ONBOARDING_DIR / key
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(content)
    return str(dest.relative_to(_UPLOADS_ROOT))


def _client_error_code(exc: ClientError) -> str | None:
    response = getattr(exc, "response", None) or {}
    error = response.get("Error", {}) if isinstance(response, dict) else {}
    return error.get("Code")


async def read_bytes(ref: str) -> bytes:
    """Return the raw bytes for a stored ref (R2 or disk).

    R2 failures are translated into the same exceptions the disk branch
    raises so the router maps them uniformly: a missing object → 404, any
    other storage/transport failure → 503. Without this a botocore
    ``ClientError`` (e.g. ``NoSuchKey``) would surface as an opaque 500.
    """
    if ref.startswith(_OBJ_PREFIX):
        key = ref[len(_OBJ_PREFIX) :]
        try:
            return await download_object_bytes(key)
        except ClientError as exc:
            if _client_error_code(exc) in ("NoSuchKey", "404", "NotFound"):
                raise FileNotFoundError(f"object not found: {key}") from exc
            raise RuntimeError("object storage unavailable") from exc
    try:
        return (_UPLOADS_ROOT / ref).read_bytes()
    except FileNotFoundError:
        raise  # missing file → 404 (the router maps FileNotFoundError)
    except OSError as exc:
        # An unreadable file / disk error (e.g. PermissionError) is an OSError
        # but NOT FileNotFoundError, so without this it would escape both the
        # router's 404 and 503 handlers as an opaque 500. Normalize it to a
        # RuntimeError → 503, mirroring the R2 branch's ClientError handling.
        raise RuntimeError("storage unavailable") from exc


async def serve(ref: str) -> bytes:
    """Phase 1: proxy the bytes (callers wrap in a Response)."""
    return await read_bytes(ref)


async def exists(ref: str) -> bool:
    """Return True iff the stored object/file is present."""
    if ref.startswith(_OBJ_PREFIX):
        return await object_exists(ref[len(_OBJ_PREFIX) :])
    return (_UPLOADS_ROOT / ref).exists()


async def delete(ref: str) -> None:
    """Best-effort delete of a stored ref (R2 swallows failures)."""
    if ref.startswith(_OBJ_PREFIX):
        await delete_object(ref[len(_OBJ_PREFIX) :])
        return
    path = _UPLOADS_ROOT / ref
    if path.exists():
        path.unlink()
