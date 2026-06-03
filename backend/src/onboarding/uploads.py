"""Fill-time file-upload fence for ``upload_request`` documents (v3, P0-6).

A client uploads each file to ``POST /{token}/documents/{id}/files``; this
module is the service core behind that route (and the matching DELETE). Every
file is hardened then landed as its OWN ``contacts`` Attachment + an
``onboarding_packet_uploads`` row, and its row id is appended to
``field_values[field_id]``. Because each file is attached at FILL time, the
parent document's 1:1 ``attachment_id`` fence stays reserved for the single
completion manifest — so a Phase-B retry never duplicates uploaded files.

Hardening (§D.4), all enforced BEFORE the file touches storage:
  * extension allow-list (the ``contacts`` ``PER_ENTITY_ALLOWED_EXTENSIONS``
    set: pdf/png/jpg/jpeg/webp/gif/docx — confirmed v1, §F #4);
  * magic-byte sniff (``sniff_magic_bytes``) — a renamed SVG/HTML/executable is
    rejected even with a whitelisted extension (stored-XSS);
  * the field's ``maxMB`` per file + ``maxFiles`` per field;
  * a per-PACKET aggregate byte cap (Form-3 designer assets ≈ 500 MB).

A ``sensitive: true`` field (gov-ID) lands its Attachment under
``category='onboarding_sensitive'`` so the download route gates it owner/admin
only, and marks the fence row ``sensitive=True`` (leaves the seam for a future
``completed_at + Nd`` retention sweep — NOT built in v1, §F #2).
"""

from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING

from sqlalchemy import func, select

from src.attachments.service import (
    ONBOARDING_UPLOAD_EXTENSIONS,
    AttachmentService,
    sniff_magic_bytes,
)
from src.onboarding.models import (
    OnboardingPacketDocument,
    OnboardingPacketUpload,
)
from src.onboarding.packet_errors import PacketValidationError
from src.onboarding.packet_schemas import FileDeleteResult, FileUploadResult
from src.onboarding.tokens import hash_token

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from src.onboarding.models import OnboardingPacket

# Sum of all uploaded bytes across one packet's documents. A single Form-3 of
# designer assets is the worst case (~500 MB); a generous ceiling that still
# bounds the storage a single token can consume.
MAX_PACKET_UPLOAD_BYTES = 500 * 1024 * 1024
_MB = 1024 * 1024


def _get_extension(filename: str) -> str:
    return filename.rsplit(".", 1)[-1].lower() if "." in filename else ""


def _file_field(doc: OnboardingPacketDocument, field_id: str) -> dict:
    """Return the ``file_upload`` field def for ``field_id`` or 422."""
    for field in doc.field_definitions or []:
        if field.get("id") == field_id:
            if field.get("kind") != "file_upload":
                raise PacketValidationError(
                    f"Field '{field_id}' does not accept file uploads"
                )
            return field
    raise PacketValidationError(f"Unknown upload field '{field_id}'")


async def _packet_uploaded_bytes(db: AsyncSession, packet_id: int) -> int:
    """Total bytes already uploaded across every document in the packet."""
    total = (
        await db.execute(
            select(func.coalesce(func.sum(OnboardingPacketUpload.byte_size), 0))
            .select_from(OnboardingPacketUpload)
            .join(
                OnboardingPacketDocument,
                OnboardingPacketUpload.packet_document_id
                == OnboardingPacketDocument.id,
            )
            .where(OnboardingPacketDocument.packet_id == packet_id)
        )
    ).scalar_one()
    return int(total or 0)


async def _field_upload_count(
    db: AsyncSession, doc_id: int, field_id: str
) -> int:
    return int(
        (
            await db.execute(
                select(func.count())
                .select_from(OnboardingPacketUpload)
                .where(OnboardingPacketUpload.packet_document_id == doc_id)
                .where(OnboardingPacketUpload.field_id == field_id)
            )
        ).scalar_one()
        or 0
    )


def _field_upload_ids(doc: OnboardingPacketDocument, field_id: str) -> list[int]:
    """The current upload-id list stored under ``field_values[field_id]``."""
    raw = (doc.field_values or {}).get(field_id)
    if isinstance(raw, list):
        return [v for v in raw if isinstance(v, int) and not isinstance(v, bool)]
    return []


def _set_field_upload_ids(
    doc: OnboardingPacketDocument, field_id: str, ids: list[int]
) -> None:
    """Whole-replace ``field_values`` (JSONB is reassigned, never mutated in
    place — the ORM tracks the new dict identity)."""
    merged = dict(doc.field_values or {})
    if ids:
        merged[field_id] = ids
    else:
        merged.pop(field_id, None)
    doc.field_values = merged


async def store_document_upload(
    db: AsyncSession,
    *,
    packet: OnboardingPacket,
    doc: OnboardingPacketDocument,
    field_id: str,
    original_filename: str,
    content: bytes,
    token: str,
) -> FileUploadResult:
    """Validate + land one uploaded file; append its id to ``field_values``.

    Raises ``PacketValidationError`` (→ 422) on any allow-list / magic-byte /
    cap breach, BEFORE any storage write. Returns the new upload id + the full
    id list for the field.
    """
    field = _file_field(doc, field_id)

    if not content:
        raise PacketValidationError("Refusing to store an empty file")

    ext = _get_extension(original_filename)
    if ext not in ONBOARDING_UPLOAD_EXTENSIONS:
        raise PacketValidationError(
            f"File type '.{ext}' is not allowed. "
            f"Allowed: {', '.join(sorted(ONBOARDING_UPLOAD_EXTENSIONS))}"
        )
    if not sniff_magic_bytes(content, ext):
        # The bytes don't match the claimed type (renamed SVG/HTML/exe etc.).
        raise PacketValidationError(
            "File content does not match its type and was rejected."
        )

    # Per-file maxMB (the field def is author-validated to a positive int).
    max_mb = field.get("maxMB")
    if isinstance(max_mb, int) and not isinstance(max_mb, bool) and max_mb > 0:
        if len(content) > max_mb * _MB:
            raise PacketValidationError(
                f"File exceeds the {max_mb} MB limit for this field."
            )

    # Per-field maxFiles.
    max_files = field.get("maxFiles")
    current_count = await _field_upload_count(db, doc.id, field_id)
    if (
        isinstance(max_files, int)
        and not isinstance(max_files, bool)
        and max_files > 0
        and current_count >= max_files
    ):
        raise PacketValidationError(
            f"At most {max_files} file(s) may be uploaded for this field."
        )

    # Per-packet aggregate cap.
    already = await _packet_uploaded_bytes(db, packet.id)
    if already + len(content) > MAX_PACKET_UPLOAD_BYTES:
        raise PacketValidationError(
            "This onboarding link has reached its total upload limit."
        )

    sensitive = bool(field.get("sensitive"))
    category = "onboarding_sensitive" if sensitive else "onboarding"
    mime_type = _MIME_BY_EXT.get(ext, "application/octet-stream")

    attachment = await AttachmentService(db).create_from_bytes(
        content=content,
        original_filename=original_filename,
        entity_type="contacts",
        entity_id=packet.contact_id,
        category=category,
        uploaded_by=None,
        mime_type=mime_type,
    )

    upload = OnboardingPacketUpload(
        packet_document_id=doc.id,
        field_id=field_id,
        attachment_id=attachment.id,
        original_filename=original_filename[:255],
        byte_size=len(content),
        content_sha256=hashlib.sha256(content).hexdigest(),
        mime_type=mime_type,
        sensitive=sensitive,
        token_hash=hash_token(token),
    )
    db.add(upload)
    await db.flush()  # assign upload.id

    ids = _field_upload_ids(doc, field_id)
    ids.append(upload.id)
    _set_field_upload_ids(doc, field_id, ids)

    return FileUploadResult(
        upload_id=upload.id,
        field_id=field_id,
        original_filename=upload.original_filename,
        byte_size=upload.byte_size,
        mime_type=upload.mime_type,
        field_uploads=ids,
    )


async def delete_document_upload(
    db: AsyncSession, *, doc: OnboardingPacketDocument, upload_id: int
) -> FileDeleteResult:
    """Delete one uploaded file (Attachment + row) and drop it from the answer.

    404-equivalent (422) if the upload doesn't belong to this document — never
    lets a forwarded link delete another document's file by id guessing.
    """
    upload = (
        await db.execute(
            select(OnboardingPacketUpload)
            .where(OnboardingPacketUpload.id == upload_id)
            .where(OnboardingPacketUpload.packet_document_id == doc.id)
        )
    ).scalar_one_or_none()
    if upload is None:
        raise PacketValidationError("Uploaded file not found for this document.")

    field_id = upload.field_id
    attachments = AttachmentService(db)
    if upload.attachment_id is not None:
        attachment = await attachments.get_attachment(upload.attachment_id)
        if attachment is not None:
            await attachments.delete_attachment(attachment)
    await db.delete(upload)
    await db.flush()

    ids = [i for i in _field_upload_ids(doc, field_id) if i != upload_id]
    _set_field_upload_ids(doc, field_id, ids)

    return FileDeleteResult(deleted=True, field_id=field_id, field_uploads=ids)


# Stable, allow-list-bounded MIME per accepted extension (never trust the
# client's declared Content-Type — derive it from the verified extension).
_MIME_BY_EXT: dict[str, str] = {
    "pdf": "application/pdf",
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "webp": "image/webp",
    "gif": "image/gif",
    "docx": (
        "application/vnd.openxmlformats-officedocument."
        "wordprocessingml.document"
    ),
}
