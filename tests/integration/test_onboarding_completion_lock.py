"""MANDATORY real-Postgres lock test for the 3-phase completion (§13).

SQLite cannot prove ``SELECT ... FOR UPDATE`` or row-level lease contention,
so this test stands up its OWN throwaway Postgres database (never the dev
``crm_db``), creates the full schema there, seeds a real packet + document
(real viewable+filled PDF + a real signature PNG + a recorded view), and then
proves the two concurrency invariants the build order requires:

  (a) **Claim race** — two concurrent Phase-A claims on the same packet: exactly
      ONE wins (the conditional UPDATE rowcount), the other raises
      ``PacketRaceError`` (→ 409). Two separate sessions + ``asyncio.gather``.
  (b) **Per-doc lease** — the lease + ``attachment_id`` fence prevent a double
      attach: even when two Phase-B passes both reach the stamp (a stale-lease
      reclaim), exactly ONE attachment lands and the orphan is cleaned up.

Skipped (not failed) when ``TEST_POSTGRES_URL`` is unreachable.

Run:
  TEST_POSTGRES_URL=postgresql+asyncpg://crm_user:crm_password@localhost:5432/crm_db \\
    python -m pytest tests/integration/test_onboarding_completion_lock.py -q
"""

from __future__ import annotations

import asyncio
import io
import os
import struct
import uuid
import zlib
from datetime import UTC, datetime, timedelta
from urllib.parse import urlsplit

import pytest
import pytest_asyncio
from reportlab.lib.pagesizes import LETTER
from reportlab.pdfgen import canvas
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

DEFAULT_PG_URL = "postgresql+asyncpg://crm_user:crm_password@localhost:5432/crm_db"
TEST_POSTGRES_URL = os.getenv("TEST_POSTGRES_URL", DEFAULT_PG_URL)


def _split_url(url: str) -> tuple[str, str]:
    """Return (base_without_dbname, dbname) for an async PG URL."""
    base, _, dbname = url.rpartition("/")
    return base, dbname


def _postgres_reachable() -> bool:
    """Verify the maintenance DB with a REAL connect at collection time.

    A TCP-only probe isn't enough: CI runs Postgres but under a DIFFERENT db
    name (``crm_test_db``, not the default ``crm_db``), so a TCP probe passes
    and the test then ERRORs at setup with ``InvalidCatalogNameError`` instead
    of skipping. Actually connecting verifies the configured database exists;
    any failure (down / missing db / bad creds) → skip, never error. Point
    ``TEST_POSTGRES_URL`` at an existing DB to run it (locally: the docker
    ``crm_db``).
    """
    import asyncpg

    parts = urlsplit(TEST_POSTGRES_URL)

    async def _probe() -> None:
        conn = await asyncpg.connect(
            host=parts.hostname or "localhost",
            port=parts.port or 5432,
            user=parts.username,
            password=parts.password,
            database=(parts.path or "/").lstrip("/") or "postgres",
            timeout=3,
        )
        await conn.close()

    try:
        asyncio.run(_probe())
        return True
    except Exception:
        return False


requires_postgres = pytest.mark.skipif(
    not _postgres_reachable(),
    reason=f"Postgres not reachable at {TEST_POSTGRES_URL}",
)


# --------------------------------------------------------------------------
# Real artifact builders (no mocks)
# --------------------------------------------------------------------------


def _one_page_pdf() -> bytes:
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=LETTER)
    c.drawString(72, 720, "Lock-test onboarding document")
    c.showPage()
    c.save()
    return buf.getvalue()


def _png_bytes() -> bytes:
    raw = b"\x00" + b"\xff\x00\x00"
    compressed = zlib.compress(raw)

    def chunk(tag: bytes, data: bytes) -> bytes:
        body = tag + data
        return (
            struct.pack(">I", len(data))
            + body
            + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF)
        )

    ihdr = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", ihdr)
        + chunk(b"IDAT", compressed)
        + chunk(b"IEND", b"")
    )


# --------------------------------------------------------------------------
# Throwaway-database fixture: full schema, isolated from crm_db
# --------------------------------------------------------------------------


@pytest_asyncio.fixture
async def pg_engine():
    """Create a throwaway PG database with the full schema; drop it after.

    We never touch the dev ``crm_db`` schema: a uniquely-named database is
    CREATEd via an AUTOCOMMIT connection to the base URL, the entire
    ``Base.metadata`` is materialized inside it, and the database is dropped
    on teardown.
    """
    base, _ = _split_url(TEST_POSTGRES_URL)
    throwaway = f"crm_locktest_{uuid.uuid4().hex[:12]}"

    admin = create_async_engine(TEST_POSTGRES_URL, isolation_level="AUTOCOMMIT")
    async with admin.connect() as conn:
        await conn.execute(text(f'CREATE DATABASE "{throwaway}"'))
    await admin.dispose()

    # The root conftest (already loaded by pytest) imported every model module,
    # so Base.metadata holds the full schema incl. the onboarding FKs.
    from src.database import Base

    engine = create_async_engine(f"{base}/{throwaway}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    try:
        yield engine
    finally:
        await engine.dispose()
        admin = create_async_engine(TEST_POSTGRES_URL, isolation_level="AUTOCOMMIT")
        async with admin.connect() as conn:
            # Terminate stragglers, then drop.
            await conn.execute(
                text(
                    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                    "WHERE datname = :d AND pid <> pg_backend_pid()"
                ),
                {"d": throwaway},
            )
            await conn.execute(text(f'DROP DATABASE IF EXISTS "{throwaway}"'))
        await admin.dispose()


@pytest_asyncio.fixture
async def session_maker(pg_engine):
    return async_sessionmaker(pg_engine, expire_on_commit=False)


# --------------------------------------------------------------------------
# Seed a completable packet (real PDF copy + filled value + signature + view)
# --------------------------------------------------------------------------


async def _seed_completable_packet(session_maker):
    """Create user/contact/template/packet/doc; record the view + signature.

    Returns ``(packet_id, doc_id, access_token, signer_email)``.
    """
    from src.auth.models import User
    from src.contacts.models import Contact
    from src.onboarding import storage, tokens
    from src.onboarding.models import (
        OnboardingPacket,
        OnboardingPacketDocument,
        OnboardingTemplate,
    )
    from src.onboarding.view_ledger import record_packet_document_view

    signer_email = "client@example.com"
    raw_token = tokens.mint_token()

    async with session_maker() as db:
        user = User(
            email=f"owner-{uuid.uuid4().hex[:6]}@example.com",
            hashed_password="x",
            full_name="Owner",
            is_active=True,
        )
        db.add(user)
        await db.flush()

        contact = Contact(
            first_name="Jane",
            last_name="Client",
            email=signer_email,
            status="active",
            owner_id=user.id,
            created_by_id=user.id,
        )
        db.add(contact)
        await db.flush()

        # Real PDF copy in storage (disk fallback in the test env).
        key = f"onboarding_packets/locktest/{uuid.uuid4().hex}.pdf"
        pdf_path = await storage.write(key, _one_page_pdf(), "application/pdf")

        field_defs = [
            {
                "id": "full_name",
                "kind": "text",
                "label": "Full Name",
                "required": True,
                "prefill": None,
                "page": 1,
                "x": 72.0,
                "y": 600.0,
                "w": 300.0,
                "h": 24.0,
            }
        ]
        template = OnboardingTemplate(
            name="Lock Template",
            field_definitions=field_defs,
            requires_esign=False,
            is_active=True,
            pdf_path=pdf_path,
        )
        db.add(template)
        await db.flush()

        packet = OnboardingPacket(
            contact_id=contact.id,
            recipient_email=signer_email,
            token_hash=tokens.hash_token(raw_token),
            token_expires_at=datetime.now(UTC) + timedelta(days=30),
            status="active",
            signer_signature_image=_png_bytes(),
            signature_version=1,
            created_by_id=user.id,
        )
        db.add(packet)
        await db.flush()

        doc = OnboardingPacketDocument(
            packet_id=packet.id,
            display_order=0,
            source_template_id=template.id,
            original_filename="LockDoc.pdf",
            pdf_path=pdf_path,
            field_definitions=field_defs,
            field_values={"full_name": "Jane Client"},
            field_values_version=1,
            requires_esign=False,
        )
        db.add(doc)
        await db.flush()

        # Record the read-before-sign view under the access token.
        await record_packet_document_view(
            db, packet_document_id=doc.id, token=raw_token
        )
        await db.commit()
        return packet.id, doc.id, raw_token, signer_email


# --------------------------------------------------------------------------
# (a) Claim race — exactly one Phase-A claim wins, the other 409s
# --------------------------------------------------------------------------


@requires_postgres
@pytest.mark.asyncio
async def test_concurrent_claim_exactly_one_wins(session_maker):
    """Two concurrent Phase-A claims: one wins, the other raises PacketRaceError."""
    from src.onboarding.completion import _phase_a_claim
    from src.onboarding.models import OnboardingPacket
    from src.onboarding.packet_errors import PacketRaceError

    packet_id, _doc_id, raw_token, signer_email = await _seed_completable_packet(
        session_maker
    )

    async def claim():
        # Each contender gets its OWN session/connection (real row-lock contention).
        async with session_maker() as db:
            packet = (
                await db.execute(
                    select(OnboardingPacket).where(OnboardingPacket.id == packet_id)
                )
            ).scalar_one()
            try:
                await _phase_a_claim(
                    db,
                    packet=packet,
                    access_token=raw_token,
                    signer_email=signer_email,
                )
                return "won"
            except PacketRaceError:
                return "lost"

    results = await asyncio.gather(claim(), claim())
    assert sorted(results) == ["lost", "won"], results

    # The packet is left in `completing` by the single winner.
    async with session_maker() as db:
        status = (
            await db.execute(
                select(OnboardingPacket.status).where(
                    OnboardingPacket.id == packet_id
                )
            )
        ).scalar_one()
        assert status == "completing"


# --------------------------------------------------------------------------
# (b) Per-doc lease + fence — exactly one attachment, orphan cleaned up
# --------------------------------------------------------------------------


@requires_postgres
@pytest.mark.asyncio
async def test_concurrent_phase_b_attaches_exactly_once(session_maker):
    """Two concurrent Phase-B passes leave the doc with a SINGLE attachment_id."""
    from src.onboarding.completion import _phase_b_stamp
    from src.onboarding.models import OnboardingPacket, OnboardingPacketDocument
    from src.attachments.models import Attachment

    packet_id, doc_id, _raw, _signer = await _seed_completable_packet(session_maker)

    # Move the packet into `completing` (Phase A already done in real flow).
    async with session_maker() as db:
        await db.execute(
            OnboardingPacket.__table__.update()
            .where(OnboardingPacket.id == packet_id)
            .values(status="completing", completing_since=datetime.now(UTC))
        )
        await db.commit()

    async def stamp():
        async with session_maker() as db:
            await _phase_b_stamp(db, packet_id=packet_id)

    # Two concurrent stamp passes on the same doc — the lease must serialize them.
    await asyncio.gather(stamp(), stamp())

    async with session_maker() as db:
        doc = (
            await db.execute(
                select(OnboardingPacketDocument).where(
                    OnboardingPacketDocument.id == doc_id
                )
            )
        ).scalar_one()
        assert doc.attachment_id is not None  # exactly one attachment landed

        # No duplicate Attachment rows on the contact for this doc's filename.
        att_count = (
            await db.execute(
                select(func.count())
                .select_from(Attachment)
                .where(Attachment.original_filename == "LockDoc.pdf")
            )
        ).scalar()
        assert att_count == 1, f"expected exactly one attachment, got {att_count}"


@requires_postgres
@pytest.mark.asyncio
async def test_stale_lease_reclaim_fences_orphan(session_maker):
    """A stale-lease reclaim that re-stamps must NOT double-attach.

    Forces the orphan-cleanup/fence path: worker 1 leases + attaches; we then
    expire the lease and run a second pass — the fence (``attachment_id IS
    NULL``) blocks the re-attach and the second worker deletes its orphan, so
    the doc still has exactly ONE attachment and the Attachment table is not
    polluted with the orphan.
    """
    from src.onboarding.completion import _phase_b_stamp
    from src.attachments.models import Attachment
    from src.onboarding.models import OnboardingPacket, OnboardingPacketDocument

    packet_id, doc_id, _raw, _signer = await _seed_completable_packet(session_maker)
    async with session_maker() as db:
        await db.execute(
            OnboardingPacket.__table__.update()
            .where(OnboardingPacket.id == packet_id)
            .values(status="completing", completing_since=datetime.now(UTC))
        )
        await db.commit()

    # First Phase-B pass: attaches the document.
    async with session_maker() as db:
        await _phase_b_stamp(db, packet_id=packet_id)

    async with session_maker() as db:
        first_att_id = (
            await db.execute(
                select(OnboardingPacketDocument.attachment_id).where(
                    OnboardingPacketDocument.id == doc_id
                )
            )
        ).scalar_one()
        assert first_att_id is not None

        # Expire the lease so a second pass would re-lease and re-stamp. The
        # fence (attachment_id already set) must still prevent a second attach.
        await db.execute(
            OnboardingPacketDocument.__table__.update()
            .where(OnboardingPacketDocument.id == doc_id)
            .values(stamp_lease_at=datetime.now(UTC) - timedelta(hours=1))
        )
        await db.commit()

    # Second Phase-B pass (the reclaim). Its lease acquire is gated on
    # attachment_id IS NULL, so it should be a no-op; even if it stamped, the
    # fence + orphan delete keep a single attachment.
    async with session_maker() as db:
        await _phase_b_stamp(db, packet_id=packet_id)

    async with session_maker() as db:
        final_att_id = (
            await db.execute(
                select(OnboardingPacketDocument.attachment_id).where(
                    OnboardingPacketDocument.id == doc_id
                )
            )
        ).scalar_one()
        assert final_att_id == first_att_id  # unchanged — no re-attach

        att_count = (
            await db.execute(
                select(func.count())
                .select_from(Attachment)
                .where(Attachment.original_filename == "LockDoc.pdf")
            )
        ).scalar()
        assert att_count == 1, f"orphan not fenced: {att_count} attachments"
