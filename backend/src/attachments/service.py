"""Attachment service layer for file upload, listing, download, and deletion."""

import os
import uuid
from pathlib import Path

from fastapi import UploadFile
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.attachments.models import Attachment
from src.attachments.object_storage import (
    delete_object,
    generate_object_key,
    get_download_url,
    is_object_storage_available,
    upload_file_bytes,
)

MAX_UPLOAD_SIZE = int(os.getenv("MAX_UPLOAD_SIZE", str(10 * 1024 * 1024)))

# Cap for system-generated attachments built from in-memory bytes (a
# completed onboarding packet's stamped PDFs). Larger than MAX_UPLOAD_SIZE
# because a multi-page flattened PDF with an embedded signature image can
# legitimately exceed the 10 MB interactive-upload cap.
ONBOARDING_MAX_BYTES = 25 * 1024 * 1024

ALLOWED_EXTENSIONS = {
    "pdf", "docx", "xlsx", "csv",
    "png", "jpg", "jpeg", "gif",
    "txt", "webp",
}

# Per-entity-type narrowing of ALLOWED_EXTENSIONS. Defense in depth so a
# future caller invoking upload_file directly (script, new route, AI tool)
# can't bypass the route-level PDF guard and silently land a non-PDF on a
# proposal whose public-link recipient is supposed to read legal docs.
PER_ENTITY_ALLOWED_EXTENSIONS: dict[str, set[str]] = {
    "proposals": {"pdf"},
    "contracts": {"pdf", "png", "jpg", "jpeg", "webp", "gif"},
}

# Onboarding CLIENT uploads (gov-ID, designer assets) land as ``contacts``
# Attachments but must NOT widen — and must NOT narrow — the generic contacts
# attachment route (CRM staff still attach .txt/.csv/.xlsx notes to a contact).
# So this is a DEDICATED allow-list the onboarding ``/files`` path enforces
# itself, NOT a ``PER_ENTITY_ALLOWED_EXTENSIONS['contacts']`` entry (which would
# regress every other contacts attachment). The confirmed v1 set (§F decision
# #4): pdf/png/jpg/jpeg/webp/gif/docx only — NO svg/html/ai/eps (stored-XSS +
# sniffing surface). ``sniff_magic_bytes`` backstops the extension on that path.
ONBOARDING_UPLOAD_EXTENSIONS: frozenset[str] = frozenset(
    {"pdf", "png", "jpg", "jpeg", "webp", "gif", "docx"}
)

# Magic-byte signatures for the onboarding-upload allow-list. The KEY is the
# declared extension; a match means the leading bytes are consistent with that
# type. ``docx`` (and any future zip-container office format) is a ZIP — the
# generic ``PK\x03\x04`` header is accepted for it. This is a CONTENT sniff that
# backstops the extension allow-list; it deliberately REJECTS SVG/HTML (which
# have no binary magic) so a ``<svg onload=...>`` renamed to ``.png`` is caught.
_MAGIC_SIGNATURES: dict[str, tuple[bytes, ...]] = {
    "pdf": (b"%PDF",),
    "png": (b"\x89PNG\r\n\x1a\n",),
    "jpg": (b"\xff\xd8\xff",),
    "jpeg": (b"\xff\xd8\xff",),
    "gif": (b"GIF87a", b"GIF89a"),
    # RIFF....WEBP — the 4-byte "WEBP" tag sits at offset 8; checked specially.
    "webp": (b"RIFF",),
    # docx/xlsx/pptx are ZIP containers.
    "docx": (b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08"),
}

# Leading byte sequences that are NEVER acceptable regardless of extension —
# active-content payloads that a polyglot/renamed file could smuggle in. SVG and
# HTML are the stored-XSS vectors the plan calls out explicitly (§D.4).
_FORBIDDEN_PREFIXES: tuple[bytes, ...] = (
    b"<?xml",
    b"<svg",
    b"<!doctype",
    b"<html",
    b"<script",
    b"\x4d\x5a",  # MZ — Windows PE executable
    b"\x7fELF",   # ELF executable
)


def sniff_magic_bytes(content: bytes, ext: str) -> bool:
    """True iff ``content``'s leading bytes are consistent with ``ext``.

    Defense-in-depth backing the extension allow-list (§D.4): a file renamed
    ``payload.svg`` → ``logo.png`` is caught because its bytes don't start with
    the PNG signature, and an active-content prefix (SVG/HTML/executable) is
    rejected outright even if it somehow matched a signature. Empty content is
    rejected (an empty file has no valid magic). The check is intentionally
    lenient on the legitimate types and strict on the dangerous ones.
    """
    if not content:
        return False
    head = content[:32]
    lowered = head.lstrip().lower()
    for forbidden in _FORBIDDEN_PREFIXES:
        if lowered.startswith(forbidden):
            return False
    # Reject an embedded active-content payload ANYWHERE in the leading window,
    # not just at the very start — a GIF/JPEG polyglot (valid magic header
    # followed by ``<script>``/``<svg>``) would otherwise pass the prefix-only
    # check and the positive signature check. Real binary image data does not
    # contain these literal ASCII tag sequences in the first 2 KB.
    window = content[:2048].lower()
    for tag in (b"<script", b"<svg", b"<iframe", b"<html", b"<?php", b"<!doctype"):
        if tag in window:
            return False
    signatures = _MAGIC_SIGNATURES.get(ext.lower())
    if signatures is None:
        return False
    if ext.lower() == "webp":
        # RIFF container with the WEBP form-type tag at offset 8.
        return head[:4] == b"RIFF" and head[8:12] == b"WEBP"
    return any(head.startswith(sig) for sig in signatures)

UPLOAD_DIR = Path(__file__).parent.parent.parent / "uploads"


def _use_object_storage() -> bool:
    return is_object_storage_available()


def _get_extension(filename: str) -> str:
    return filename.rsplit(".", 1)[-1].lower() if "." in filename else ""


class AttachmentService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def upload_file(
        self,
        file: UploadFile,
        entity_type: str,
        entity_id: int,
        user_id: int,
        category: str | None = None,
    ) -> Attachment:
        ext = _get_extension(file.filename or "")
        if ext not in ALLOWED_EXTENSIONS:
            raise ValueError(
                f"File type '.{ext}' not allowed. Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}"
            )
        per_entity = PER_ENTITY_ALLOWED_EXTENSIONS.get(entity_type)
        if per_entity is not None and ext not in per_entity:
            raise ValueError(
                f"File type '.{ext}' not allowed on {entity_type}. "
                f"Allowed: {', '.join(sorted(per_entity))}"
            )

        # Reject uploads that omit Content-Length (chunked transfer encoding)
        # or whose declared size already exceeds the cap — before reading body
        # into memory. file.size is measured by Starlette during multipart
        # parsing; it is None for raw body uploads or chunked transfer encoding.
        actual_size = file.size
        if actual_size is None:
            raise ValueError("Upload rejected: Content-Length is required (chunked uploads not supported).")
        if actual_size > MAX_UPLOAD_SIZE:
            raise ValueError(
                f"File size {actual_size} bytes exceeds maximum of {MAX_UPLOAD_SIZE} bytes"
            )

        content = await file.read()
        file_size = len(content)

        if file_size > MAX_UPLOAD_SIZE:
            raise ValueError(
                f"File size {file_size} bytes exceeds maximum of {MAX_UPLOAD_SIZE} bytes"
            )

        unique_name = f"{uuid.uuid4().hex}.{ext}"
        content_type = file.content_type or "application/octet-stream"

        if _use_object_storage():
            object_key = generate_object_key(entity_type, entity_id, ext)
            await upload_file_bytes(content, object_key, content_type)
            file_path = f"obj://{object_key}"
        else:
            entity_dir = UPLOAD_DIR / entity_type / str(entity_id)
            entity_dir.mkdir(parents=True, exist_ok=True)
            disk_path = entity_dir / unique_name
            disk_path.write_bytes(content)
            file_path = str(disk_path.relative_to(UPLOAD_DIR))

        attachment = Attachment(
            filename=unique_name,
            original_filename=file.filename or unique_name,
            file_path=file_path,
            file_size=file_size,
            mime_type=content_type,
            entity_type=entity_type,
            entity_id=entity_id,
            uploaded_by=user_id,
            category=category,
        )
        self.db.add(attachment)
        await self.db.flush()
        await self.db.refresh(attachment)
        return attachment

    async def create_from_bytes(
        self,
        *,
        content: bytes,
        original_filename: str,
        entity_type: str,
        entity_id: int,
        category: str | None = None,
        uploaded_by: int | None = None,
        mime_type: str = "application/pdf",
    ) -> Attachment:
        """Create an Attachment from in-memory bytes (system-generated docs).

        Replicates ``upload_file``'s defense-in-depth (extension allow-list +
        size cap) but: takes raw bytes rather than an ``UploadFile``; enforces
        the 25 MB ``ONBOARDING_MAX_BYTES`` cap; allows ``uploaded_by=None``
        (no human uploader); and owns the SINGLE storage write via the
        onboarding storage module so the resulting ``file_path`` is a ref the
        existing download path can serve. The CALLER writes any timeline
        Activity — this method stays single-purpose (write + row + flush).
        """
        # Lazy import avoids a circular import (onboarding.storage imports
        # this module for _use_object_storage / upload_file_bytes).
        from src.onboarding import storage as onboarding_storage

        ext = _get_extension(original_filename)
        if ext not in ALLOWED_EXTENSIONS:
            raise ValueError(
                f"File type '.{ext}' not allowed. "
                f"Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}"
            )
        per_entity = PER_ENTITY_ALLOWED_EXTENSIONS.get(entity_type)
        if per_entity is not None and ext not in per_entity:
            raise ValueError(
                f"File type '.{ext}' not allowed on {entity_type}. "
                f"Allowed: {', '.join(sorted(per_entity))}"
            )

        file_size = len(content)
        if file_size == 0:
            raise ValueError("Refusing to store an empty file")
        if file_size > ONBOARDING_MAX_BYTES:
            raise ValueError(
                f"File size {file_size} bytes exceeds maximum of "
                f"{ONBOARDING_MAX_BYTES} bytes"
            )

        unique_name = f"{uuid.uuid4().hex}.{ext}"
        # Feature-namespaced key (mirrors onboarding template keys); storage
        # returns "obj://<key>" on R2 or a path relative to uploads/ on disk.
        key = f"onboarding_completed/{entity_id}/{unique_name}"
        file_path = await onboarding_storage.write(key, content, mime_type)

        attachment = Attachment(
            filename=unique_name,
            original_filename=original_filename,
            file_path=file_path,
            file_size=file_size,
            mime_type=mime_type,
            entity_type=entity_type,
            entity_id=entity_id,
            uploaded_by=uploaded_by,
            category=category,
        )
        self.db.add(attachment)
        await self.db.flush()
        await self.db.refresh(attachment)
        return attachment

    async def list_attachments(
        self,
        entity_type: str,
        entity_id: int,
        category: str | None = None,
    ) -> tuple[list[Attachment], int]:
        query = (
            select(Attachment)
            .where(Attachment.entity_type == entity_type)
            .where(Attachment.entity_id == entity_id)
        )
        if category:
            query = query.where(Attachment.category == category)
        query = query.order_by(Attachment.created_at.desc())
        result = await self.db.execute(query)
        items = list(result.scalars().all())

        count_query = (
            select(func.count())
            .select_from(Attachment)
            .where(Attachment.entity_type == entity_type)
            .where(Attachment.entity_id == entity_id)
        )
        if category:
            count_query = count_query.where(Attachment.category == category)
        count_result = await self.db.execute(count_query)
        total = count_result.scalar() or 0

        return items, total

    async def get_attachment(self, attachment_id: int) -> Attachment | None:
        result = await self.db.execute(
            select(Attachment).where(Attachment.id == attachment_id)
        )
        return result.scalar_one_or_none()

    async def delete_attachment(self, attachment: Attachment) -> None:
        if attachment.file_path.startswith("obj://"):
            object_key = attachment.file_path[6:]
            await delete_object(object_key)
        else:
            file_path = UPLOAD_DIR / attachment.file_path
            if file_path.exists():
                file_path.unlink()

        await self.db.delete(attachment)
        await self.db.flush()

    def get_file_path(self, attachment: Attachment) -> Path | None:
        if attachment.file_path.startswith("obj://"):
            return None
        return UPLOAD_DIR / attachment.file_path

    async def get_download_url(self, attachment: Attachment) -> str | None:
        if attachment.file_path.startswith("obj://"):
            object_key = attachment.file_path[6:]
            # Force an ATTACHMENT download with the original filename and a
            # generic octet-stream type so a renamed active-content file (or
            # PII) can't be sniffed + rendered inline on the presigned-URL
            # branch — matching the nosniff+attachment headers the local-disk
            # FileResponse branch already sets (PF3).
            return await get_download_url(
                object_key, filename=attachment.original_filename
            )
        return None
