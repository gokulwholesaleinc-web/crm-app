"""No-mock tests for ``AttachmentService.create_from_bytes`` (build-order §5).

The 25 MB-cap, empty-reject, ``uploaded_by=None`` system-generated path that
Phase-C completion uses to land a stamped PDF on the contact record. R2 creds
are absent in the test env, so every write takes the local-disk branch under
``uploads/onboarding_completed/`` and the bytes round-trip via
``onboarding.storage.read_bytes``. Nothing is mocked.
"""

import uuid

import pytest
from sqlalchemy import select
from src.attachments.models import Attachment
from src.attachments.service import ONBOARDING_MAX_BYTES, AttachmentService
from src.onboarding import storage

pytestmark = pytest.mark.asyncio


async def test_create_from_bytes_disk_fallback_round_trips(db_session, test_contact):
    """Should write to disk, create the Attachment row, and round-trip bytes."""
    content = b"%PDF-1.4 onboarding completed " + uuid.uuid4().bytes
    service = AttachmentService(db_session)

    att = await service.create_from_bytes(
        content=content,
        original_filename="W-9.pdf",
        entity_type="contacts",
        entity_id=test_contact.id,
        category="onboarding",
        uploaded_by=None,
        mime_type="application/pdf",
    )
    try:
        # Attachment row landed on the contact.
        assert att.id is not None
        assert att.entity_type == "contacts"
        assert att.entity_id == test_contact.id
        assert att.category == "onboarding"
        assert att.original_filename == "W-9.pdf"
        assert att.file_size == len(content)
        assert att.uploaded_by is None  # system-generated, no human uploader

        # Disk ref (not an obj:// ref in the test env) and bytes round-trip.
        assert not att.file_path.startswith("obj://")
        assert await storage.read_bytes(att.file_path) == content

        # And it is queryable as a real row.
        row = await db_session.execute(
            select(Attachment).where(Attachment.id == att.id)
        )
        assert row.scalar_one().file_path == att.file_path
    finally:
        await storage.delete(att.file_path)


async def test_create_from_bytes_rejects_empty(db_session, test_contact):
    """Should refuse to store an empty file (0 bytes)."""
    service = AttachmentService(db_session)
    with pytest.raises(ValueError):
        await service.create_from_bytes(
            content=b"",
            original_filename="empty.pdf",
            entity_type="contacts",
            entity_id=test_contact.id,
        )


async def test_create_from_bytes_rejects_over_25mb(db_session, test_contact):
    """Should reject content above the 25 MB ONBOARDING_MAX_BYTES cap.

    We assert the boundary by length WITHOUT allocating 25 MB of distinct
    bytes per run where avoidable — a single oversize buffer is fine here.
    """
    service = AttachmentService(db_session)
    oversize = b"\x00" * (ONBOARDING_MAX_BYTES + 1)
    with pytest.raises(ValueError):
        await service.create_from_bytes(
            content=oversize,
            original_filename="huge.pdf",
            entity_type="contacts",
            entity_id=test_contact.id,
        )


async def test_create_from_bytes_rejects_disallowed_extension(db_session, test_contact):
    """Should reject a filename whose extension is not in the allow-list."""
    service = AttachmentService(db_session)
    with pytest.raises(ValueError):
        await service.create_from_bytes(
            content=b"not really an exe",
            original_filename="payload.exe",
            entity_type="contacts",
            entity_id=test_contact.id,
        )


async def test_create_from_bytes_at_cap_is_accepted(db_session, test_contact):
    """Should accept content exactly at the cap (boundary is inclusive)."""
    service = AttachmentService(db_session)
    # Exactly at the cap: len == ONBOARDING_MAX_BYTES must pass (only > rejects).
    content = b"\x01" * ONBOARDING_MAX_BYTES
    att = await service.create_from_bytes(
        content=content,
        original_filename="at-cap.pdf",
        entity_type="contacts",
        entity_id=test_contact.id,
        uploaded_by=None,
    )
    try:
        assert att.file_size == ONBOARDING_MAX_BYTES
    finally:
        await storage.delete(att.file_path)
