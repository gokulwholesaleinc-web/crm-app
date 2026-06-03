"""Real-Postgres MIXED-KIND completion-lock test (v3 §13, F-series).

The esign-only ``test_onboarding_completion_lock.py`` proves the FOR UPDATE +
conditional-claim serialization for a single ``esign_pdf`` doc. This file proves
the SAME invariants hold once a packet spans all three v3 kinds — ``esign_pdf``
(real PDF + signature + required text), ``questionnaire`` (no PDF; Platypus
answer summary), and ``upload_request`` (no PDF; real uploaded file + manifest) —
which is the configuration the kind-dispatch refactor put at risk.

It reuses the sibling's harness verbatim: the ``requires_postgres`` skipif (a
REAL connect probe, not a TCP poke), the throwaway-database ``pg_engine`` /
``session_maker`` fixtures, and the real reportlab/PNG artifact builders. Per the
dual-connection seeding gotcha, the packet is seeded and COMMITTED through the
same ``session_maker`` the completion code reads from, in a single setup helper,
so every later session sees it.

Asserts:
  1) one POST-equivalent ``complete_packet`` → ``completed`` with THREE doc
     artifacts (each ``%PDF``) + the uploaded PNG as its own contact attachment;
     field_values + signature scrubbed for esign, questionnaire answers RETAINED.
  2) THE LOCK — two concurrent ``complete_packet`` coroutines: exactly one
     ``completed``, the other ``PacketRaceError`` (409).
  3) a forced ``produce_artifact`` failure on ONE kind → ``completion_failed``
     cleanly; ``retry_completion`` succeeds and does NOT duplicate the upload
     rows/files (the fill-time fence).

Run:
  TEST_POSTGRES_URL=postgresql+asyncpg://crm_user:crm_password@localhost:5432/crm_db \\
    python -m pytest tests/integration/test_onboarding_completion_lock_mixed.py -q
"""

from __future__ import annotations

import asyncio
import io
import os
import struct
import uuid
import zlib
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
    base, _, dbname = url.rpartition("/")
    return base, dbname


def _postgres_reachable() -> bool:
    """REAL connect at collection time (TCP probe alone misses a missing db)."""
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
# Real artifact builders (no mocks) — same as the esign-only lock test
# --------------------------------------------------------------------------


def _one_page_pdf() -> bytes:
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=LETTER)
    c.drawString(72, 720, "Mixed-kind lock-test onboarding document")
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
# Throwaway-database fixtures — isolated from crm_db (verbatim from sibling)
# --------------------------------------------------------------------------


@pytest_asyncio.fixture
async def pg_engine():
    base, _ = _split_url(TEST_POSTGRES_URL)
    throwaway = f"crm_mixedlock_{uuid.uuid4().hex[:12]}"

    admin = create_async_engine(TEST_POSTGRES_URL, isolation_level="AUTOCOMMIT")
    async with admin.connect() as conn:
        await conn.execute(text(f'CREATE DATABASE "{throwaway}"'))
    await admin.dispose()

    # The root conftest already imported every model module → full schema.
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
# Field-definition builders for the three kinds
# --------------------------------------------------------------------------


def _esign_defs() -> list[dict]:
    """An esign doc: a required text field + a signature field (real coords)."""
    return [
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
        },
        {
            "id": "client_sig",
            "kind": "signature",
            "label": "Signature",
            "required": True,
            "prefill": None,
            "page": 1,
            "x": 72.0,
            "y": 200.0,
            "w": 220.0,
            "h": 60.0,
        },
    ]


def _questionnaire_defs() -> list[dict]:
    """One required short_text + one optional short_text (non-sensitive)."""
    return [
        {
            "id": "company_size",
            "kind": "short_text",
            "label": "Company size",
            "required": True,
            "prefill": None,
        },
        {
            "id": "referral",
            "kind": "short_text",
            "label": "How did you hear about us?",
            "required": False,
            "prefill": None,
        },
    ]


def _upload_defs() -> list[dict]:
    """One required file_upload field, maxFiles=1."""
    return [
        {
            "id": "gov_id",
            "kind": "file_upload",
            "label": "Government ID",
            "required": True,
            "prefill": None,
            "maxFiles": 1,
            "maxMB": 10,
        }
    ]


# --------------------------------------------------------------------------
# Seed a completable MIXED-KIND packet through the real services
# --------------------------------------------------------------------------


async def _seed_completable_mixed_packet(session_maker):
    """Create user/contact + 3 templates, mint a packet, then fill every doc.

    Returns ``(packet_id, {kind: doc_id}, access_token, signer_email)``.

    The packet is created via ``PacketService.create_packet`` so each doc carries
    the correct frozen ``kind`` + (esign-only) PDF copy + consent disclosure
    snapshot. Each doc is then driven to a completable fill state:
      * esign: field_values + drawn signature on the packet + consent + view
      * questionnaire: real answers in field_values + view
      * upload: a real PNG stored via ``store_document_upload`` + view
    Everything is COMMITTED before returning so the completion sessions see it.
    """
    from src.auth.models import User
    from src.contacts.models import Contact
    from src.onboarding import storage, tokens
    from src.onboarding.models import OnboardingTemplate
    from src.onboarding.packet_service import PacketService, _now
    from src.onboarding.uploads import store_document_upload
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

        # esign template carries a real PDF (needs_pdf_copy=True copies it).
        esign_key = f"onboarding_templates/mixedlock/{uuid.uuid4().hex}.pdf"
        esign_pdf_path = await storage.write(
            esign_key, _one_page_pdf(), "application/pdf"
        )
        esign_tmpl = OnboardingTemplate(
            name="Service Agreement",
            field_definitions=_esign_defs(),
            requires_esign=True,
            is_active=True,
            pdf_path=esign_pdf_path,
            kind="esign_pdf",
        )
        questionnaire_tmpl = OnboardingTemplate(
            name="Intake Questionnaire",
            field_definitions=_questionnaire_defs(),
            requires_esign=False,
            is_active=True,
            pdf_path=None,
            kind="questionnaire",
        )
        upload_tmpl = OnboardingTemplate(
            name="Document Upload",
            field_definitions=_upload_defs(),
            requires_esign=False,
            is_active=True,
            pdf_path=None,
            kind="upload_request",
        )
        db.add_all([esign_tmpl, questionnaire_tmpl, upload_tmpl])
        await db.flush()

        service = PacketService(db)
        packet, raw_token = await service.create_packet(
            created_by_id=user.id,
            contact_id=contact.id,
            recipient_email=signer_email,
            template_ids=[esign_tmpl.id, questionnaire_tmpl.id, upload_tmpl.id],
        )

        docs = await service.load_documents(packet.id)
        by_kind = {d.kind: d for d in docs}
        esign_doc = by_kind["esign_pdf"]
        questionnaire_doc = by_kind["questionnaire"]
        upload_doc = by_kind["upload_request"]

        # --- esign fill: answer + drawn signature + consent ---
        esign_doc.field_values = {"full_name": "Jane Client"}
        esign_doc.field_values_version = 1
        esign_doc.consented_at = _now()
        packet.signer_signature_image = _png_bytes()
        packet.signature_version = 1

        # --- questionnaire fill: real answers (one required, one optional) ---
        questionnaire_doc.field_values = {
            "company_size": "11-50",
            "referral": "A friend",
        }
        questionnaire_doc.field_values_version = 1

        await db.flush()

        # --- upload fill: store a real PNG (magic-byte valid) via the service ---
        await store_document_upload(
            db,
            packet=packet,
            doc=upload_doc,
            field_id="gov_id",
            original_filename="id_front.png",
            content=_png_bytes(),
            token=raw_token,
        )

        # --- a real encrypted secret row on the upload doc (any kind may carry
        # a sensitive text field; the secret table is kind-agnostic). Seeded
        # directly so retention-on-completion vs deletion-on-purge is provable.
        from src.onboarding import crypto
        from src.onboarding.models import OnboardingSecretValue

        ciphertext, key_version = crypto.encrypt_field("super-secret-value")
        db.add(
            OnboardingSecretValue(
                packet_document_id=upload_doc.id,
                field_id="secret_field",
                ciphertext=ciphertext,
                key_version=key_version,
            )
        )

        # --- record the read-before-sign view for every doc ---
        for doc in docs:
            await record_packet_document_view(
                db, packet_document_id=doc.id, token=raw_token
            )

        await db.commit()
        return (
            packet.id,
            {
                "esign_pdf": esign_doc.id,
                "questionnaire": questionnaire_doc.id,
                "upload_request": upload_doc.id,
            },
            raw_token,
            signer_email,
        )


# --------------------------------------------------------------------------
# (1) Happy path — one completion produces all three artifacts + the upload
# --------------------------------------------------------------------------


@requires_postgres
@pytest.mark.asyncio
async def test_mixed_kind_completion_attaches_three_artifacts(session_maker):
    """One complete_packet → completed; each kind lands a %PDF artifact and the
    collected data is RETAINED on completion (purge=False): the uploaded gov-ID
    file + its row, the secret ciphertext, and the questionnaire answers all
    survive as the deliverable. Only the esign field_values (in the stamped PDF)
    and the drawn signature are scrubbed."""
    from src.attachments.models import Attachment
    from src.onboarding import storage
    from src.onboarding.completion import complete_packet
    from src.onboarding.models import (
        OnboardingPacket,
        OnboardingPacketDocument,
        OnboardingPacketUpload,
        OnboardingSecretValue,
    )

    packet_id, doc_ids, raw_token, signer_email = (
        await _seed_completable_mixed_packet(session_maker)
    )

    # BEFORE completion: the uploaded PNG is its OWN contact attachment (landed
    # at fill time via store_document_upload), distinct from the manifest the
    # upload doc will produce — so the contact carries exactly 1 attachment now.
    async with session_maker() as db:
        contact_id = (
            await db.execute(
                select(OnboardingPacket.contact_id).where(
                    OnboardingPacket.id == packet_id
                )
            )
        ).scalar_one()
        png_atts = (
            await db.execute(
                select(Attachment).where(Attachment.original_filename == "id_front.png")
            )
        ).scalars().all()
        assert len(png_atts) == 1
        png_bytes = await storage.read_bytes(png_atts[0].file_path)
        assert png_bytes.startswith(b"\x89PNG")
        pre_total = (
            await db.execute(
                select(func.count())
                .select_from(Attachment)
                .where(Attachment.entity_type == "contacts")
                .where(Attachment.entity_id == contact_id)
            )
        ).scalar()
        assert pre_total == 1, f"expected 1 fill-time attachment, got {pre_total}"

    async with session_maker() as db:
        packet = (
            await db.execute(
                select(OnboardingPacket).where(OnboardingPacket.id == packet_id)
            )
        ).scalar_one()
        result = await complete_packet(
            db,
            packet=packet,
            access_token=raw_token,
            signer_email=signer_email,
        )
    assert result["status"] == "completed", result

    async with session_maker() as db:
        docs = (
            await db.execute(
                select(OnboardingPacketDocument)
                .where(OnboardingPacketDocument.packet_id == packet_id)
                .order_by(OnboardingPacketDocument.display_order)
            )
        ).scalars().all()
        # Every doc got its own completion artifact.
        assert len(docs) == 3
        assert all(d.attachment_id is not None for d in docs), [
            (d.kind, d.attachment_id) for d in docs
        ]

        # Each completion artifact is a real PDF (esign stamp, questionnaire
        # summary, upload manifest) — proving every kind's produce_artifact ran.
        kinds_seen = set()
        for doc in docs:
            att = (
                await db.execute(
                    select(Attachment).where(Attachment.id == doc.attachment_id)
                )
            ).scalar_one()
            artifact = await storage.read_bytes(att.file_path)
            assert artifact.startswith(b"%PDF"), f"{doc.kind} artifact not a PDF"
            kinds_seen.add(doc.kind)
        assert kinds_seen == {"esign_pdf", "questionnaire", "upload_request"}

        # RETENTION on completion (purge=False): the collected data IS the
        # deliverable Lorenzo accesses, so it is KEPT. The contact now carries
        # the 3 generated artifacts PLUS the retained uploaded gov-ID file = 4.
        post_total = (
            await db.execute(
                select(func.count())
                .select_from(Attachment)
                .where(Attachment.entity_type == "contacts")
                .where(Attachment.entity_id == contact_id)
            )
        ).scalar()
        assert post_total == 4, (
            f"expected 4 (3 artifacts + retained upload), got {post_total}"
        )

        # The uploaded file's Attachment AND its onboarding_packet_uploads row
        # still exist (F1-CONFIRMED: keep gov-ID indefinitely — deleting it on
        # completion would destroy the very thing the form collected).
        png_after = (
            await db.execute(
                select(Attachment).where(Attachment.original_filename == "id_front.png")
            )
        ).scalars().all()
        assert len(png_after) == 1, "uploaded file must be RETAINED on completion"
        retained_png = await storage.read_bytes(png_after[0].file_path)
        assert retained_png.startswith(b"\x89PNG")
        upload_rows = (
            await db.execute(
                select(func.count()).select_from(OnboardingPacketUpload)
            )
        ).scalar()
        assert upload_rows == 1, "the upload fence row must be RETAINED"

        # The secret ciphertext row is RETAINED too (the decrypt route must keep
        # working post-completion — F4 passwords are part of the deliverable).
        secret_rows = (
            await db.execute(
                select(func.count()).select_from(OnboardingSecretValue)
            )
        ).scalar()
        assert secret_rows == 1, "secret ciphertext must be RETAINED on completion"

        # Scrub rules differ by kind (§C.5): esign field_values nulled + the
        # drawn signature gone (both already captured in the stamped PDF);
        # questionnaire NON-sensitive answers RETAINED as structured intake.
        by_kind = {d.kind: d for d in docs}
        assert by_kind["esign_pdf"].field_values == {}
        assert by_kind["questionnaire"].field_values == {
            "company_size": "11-50",
            "referral": "A friend",
        }
        packet = (
            await db.execute(
                select(OnboardingPacket).where(OnboardingPacket.id == packet_id)
            )
        ).scalar_one()
        assert packet.status == "completed"
        assert packet.signer_signature_image is None


# --------------------------------------------------------------------------
# (2) THE LOCK — two concurrent completions: one wins, the other 409s
# --------------------------------------------------------------------------


@requires_postgres
@pytest.mark.asyncio
async def test_mixed_kind_concurrent_complete_exactly_one_wins(session_maker):
    """Two concurrent complete_packet() on the same mixed packet → exactly one
    completed, the other PacketRaceError (the FOR UPDATE + conditional claim
    serialization holds across mixed kinds)."""
    from src.onboarding.completion import complete_packet
    from src.onboarding.models import OnboardingPacket
    from src.onboarding.packet_errors import PacketRaceError

    packet_id, _doc_ids, raw_token, signer_email = (
        await _seed_completable_mixed_packet(session_maker)
    )

    async def run_complete():
        # Each contender gets its OWN session/connection (real row contention).
        async with session_maker() as db:
            packet = (
                await db.execute(
                    select(OnboardingPacket).where(OnboardingPacket.id == packet_id)
                )
            ).scalar_one()
            try:
                result = await complete_packet(
                    db,
                    packet=packet,
                    access_token=raw_token,
                    signer_email=signer_email,
                )
                return result.get("status")
            except PacketRaceError:
                return "race"

    outcomes = await asyncio.gather(run_complete(), run_complete())
    # Exactly one durable "completed"; the loser is a clean race (409), never a
    # second completed or an opaque 500.
    assert outcomes.count("completed") == 1, outcomes
    assert "race" in outcomes or "completing" in outcomes, outcomes

    async with session_maker() as db:
        status = (
            await db.execute(
                select(OnboardingPacket.status).where(
                    OnboardingPacket.id == packet_id
                )
            )
        ).scalar_one()
        assert status == "completed"


# --------------------------------------------------------------------------
# (3) Forced artifact failure → completion_failed; retry succeeds, no dup files
# --------------------------------------------------------------------------


@requires_postgres
@pytest.mark.asyncio
async def test_forced_artifact_failure_then_retry_no_duplicate_uploads(
    session_maker, monkeypatch
):
    """A Phase-B produce_artifact failure on ONE kind → completion_failed
    cleanly; retry_completion then succeeds and does NOT duplicate the uploaded
    file rows/attachments (the fill-time fence holds across a retry)."""
    from src.attachments.models import Attachment
    from src.onboarding.completion import complete_packet, retry_completion
    from src.onboarding.kinds import get_handler
    from src.onboarding.models import (
        OnboardingPacket,
        OnboardingPacketDocument,
        OnboardingPacketUpload,
    )

    packet_id, _doc_ids, raw_token, signer_email = (
        await _seed_completable_mixed_packet(session_maker)
    )

    # Snapshot the upload-row + file-attachment count BEFORE any completion.
    async with session_maker() as db:
        uploads_before = (
            await db.execute(
                select(func.count()).select_from(OnboardingPacketUpload)
            )
        ).scalar()
        png_atts_before = (
            await db.execute(
                select(func.count())
                .select_from(Attachment)
                .where(Attachment.original_filename == "id_front.png")
            )
        ).scalar()
    assert uploads_before == 1
    assert png_atts_before == 1

    # Force the questionnaire's Phase-B artifact to blow up ONCE. The Phase-A
    # dry-run uses the same method, so we only fail on the real (non-dry) pass so
    # the claim still happens and Phase B is what fails (→ completion_failed).
    handler = get_handler("questionnaire")
    original = handler.produce_artifact
    state = {"failed": False}

    # Patched on the CLASS, so the replacement is an unbound function: it takes
    # ``self`` first, then the same (db, *, doc, packet, signature_png, dry_run)
    # the handler exposes. ``original`` is the already-bound method, so it's
    # called without ``self``.
    async def flaky_produce_artifact(
        self, db, *, doc, packet, signature_png, dry_run=False
    ):
        if not dry_run and not state["failed"]:
            state["failed"] = True
            raise RuntimeError("forced questionnaire stamp failure")
        return await original(
            db, doc=doc, packet=packet, signature_png=signature_png, dry_run=dry_run
        )

    monkeypatch.setattr(
        type(handler), "produce_artifact", flaky_produce_artifact, raising=True
    )

    # First completion: Phase B fails on the questionnaire → completion_failed.
    async with session_maker() as db:
        packet = (
            await db.execute(
                select(OnboardingPacket).where(OnboardingPacket.id == packet_id)
            )
        ).scalar_one()
        result = await complete_packet(
            db,
            packet=packet,
            access_token=raw_token,
            signer_email=signer_email,
        )
    assert result["status"] == "completion_failed", result

    async with session_maker() as db:
        status = (
            await db.execute(
                select(OnboardingPacket.status).where(
                    OnboardingPacket.id == packet_id
                )
            )
        ).scalar_one()
        assert status == "completion_failed"

        # FENCE CHECK #1 (pre-scrub): the failed pass did NOT re-store or
        # duplicate the uploaded file — still exactly the one fill-time row +
        # one PNG attachment. completion_failed does not scrub, so the row is
        # still here to count (the scrub only runs on a successful Phase C).
        uploads_at_failure = (
            await db.execute(
                select(func.count()).select_from(OnboardingPacketUpload)
            )
        ).scalar()
        assert uploads_at_failure == uploads_before == 1, uploads_at_failure
        png_at_failure = (
            await db.execute(
                select(func.count())
                .select_from(Attachment)
                .where(Attachment.original_filename == "id_front.png")
            )
        ).scalar()
        assert png_at_failure == 1, png_at_failure

    # Retry: the forced failure already fired once, so the questionnaire now
    # renders for real and the retry should drive to completed.
    async with session_maker() as db:
        packet = (
            await db.execute(
                select(OnboardingPacket).where(OnboardingPacket.id == packet_id)
            )
        ).scalar_one()
        retry_result = await retry_completion(db, packet=packet)
    assert retry_result["status"] == "completed", retry_result

    async with session_maker() as db:
        # All three docs attached after the retry (incl. the questionnaire that
        # failed the first pass — its retry rendered for real).
        docs = (
            await db.execute(
                select(OnboardingPacketDocument).where(
                    OnboardingPacketDocument.packet_id == packet_id
                )
            )
        ).scalars().all()
        assert all(d.attachment_id is not None for d in docs)

        # FENCE CHECK #2 (post-completion): completion RETAINS the upload
        # (purge=False), and the fill-time fence means Phase B NEVER re-uploads
        # it — so the row count is PRESERVED at exactly 1: not scrubbed, and
        # crucially not DUPLICATED by the failed-then-retried run.
        uploads_after = (
            await db.execute(
                select(func.count()).select_from(OnboardingPacketUpload)
            )
        ).scalar()
        assert uploads_after == uploads_before == 1, (
            f"upload row not preserved exactly once: {uploads_after}"
        )
        png_atts_after = (
            await db.execute(
                select(func.count())
                .select_from(Attachment)
                .where(Attachment.original_filename == "id_front.png")
            )
        ).scalar()
        assert png_atts_after == 1, png_atts_after  # retained, never duplicated

        # The three completion artifacts are present and not duplicated: exactly
        # three distinct attachment ids for the three docs.
        completion_att_ids = {d.attachment_id for d in docs}
        assert len(completion_att_ids) == 3


# --------------------------------------------------------------------------
# (4) PURGE side — the deletion path that DOES destroy collected PII
# --------------------------------------------------------------------------


@requires_postgres
@pytest.mark.asyncio
async def test_purge_pii_deletes_uploads_and_secrets(session_maker):
    """purge_pii (purge=True) DESTROYS the collected PII the completion retains:
    the uploaded file's Attachment + onboarding_packet_uploads row + the
    onboarding_secret_values ciphertext are deleted, the drawn signature is
    nulled, and the esign + upload answers are nulled. This is the non-delivery
    terminal path (revoke / expire / abandon / staff purge), the inverse of the
    retain-on-completion behavior proven above."""
    from src.attachments.models import Attachment
    from src.onboarding.models import (
        OnboardingPacket,
        OnboardingPacketDocument,
        OnboardingPacketUpload,
        OnboardingSecretValue,
    )
    from src.onboarding.packet_service import PacketService

    packet_id, _doc_ids, _raw_token, _signer = (
        await _seed_completable_mixed_packet(session_maker)
    )

    # Precondition: the fill-time upload + secret are present BEFORE the purge.
    async with session_maker() as db:
        assert (
            await db.execute(
                select(func.count()).select_from(OnboardingPacketUpload)
            )
        ).scalar() == 1
        assert (
            await db.execute(
                select(func.count()).select_from(OnboardingSecretValue)
            )
        ).scalar() == 1
        assert (
            await db.execute(
                select(func.count())
                .select_from(Attachment)
                .where(Attachment.original_filename == "id_front.png")
            )
        ).scalar() == 1

    # Staff purge (purge=True): destroy the collected PII, status unchanged.
    async with session_maker() as db:
        packet = (
            await db.execute(
                select(OnboardingPacket).where(OnboardingPacket.id == packet_id)
            )
        ).scalar_one()
        await PacketService(db).purge_pii(packet)
        await db.commit()

    async with session_maker() as db:
        # The uploaded file Attachment + its fence row are GONE.
        assert (
            await db.execute(
                select(func.count())
                .select_from(Attachment)
                .where(Attachment.original_filename == "id_front.png")
            )
        ).scalar() == 0, "upload Attachment should be purged"
        assert (
            await db.execute(
                select(func.count()).select_from(OnboardingPacketUpload)
            )
        ).scalar() == 0, "upload fence row should be purged"

        # The secret ciphertext row is GONE (kind-agnostic secret deletion).
        assert (
            await db.execute(
                select(func.count()).select_from(OnboardingSecretValue)
            )
        ).scalar() == 0, "secret ciphertext should be purged"

        # Signature nulled; EVERY kind's answers nulled on purge — esign, upload
        # refs, AND the questionnaire answers (under purge=True the structured
        # intake is PII to destroy, unlike the retain-on-completion path).
        packet = (
            await db.execute(
                select(OnboardingPacket).where(OnboardingPacket.id == packet_id)
            )
        ).scalar_one()
        assert packet.signer_signature_image is None
        by_kind = {
            d.kind: d
            for d in (
                await db.execute(
                    select(OnboardingPacketDocument).where(
                        OnboardingPacketDocument.packet_id == packet_id
                    )
                )
            ).scalars().all()
        }
        assert by_kind["esign_pdf"].field_values == {}
        assert by_kind["upload_request"].field_values == {}
        assert by_kind["questionnaire"].field_values == {}
