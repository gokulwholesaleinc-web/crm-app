"""3-phase ``/complete`` orchestration + per-document atomic lease.

Why three short transactions instead of one (see build-order §1, §4):

  * **Phase A** — claim the packet under a row lock. ``SELECT ... FOR UPDATE``
    on the packet AND its documents serializes concurrent ``/complete`` calls
    on real Postgres; the CLAIM is a conditional ``UPDATE`` whose ``rowcount``
    decides the winner (0 → 409). Committing here releases the lock and flips
    status to ``completing`` so PATCH/signature are rejected for the rest of
    the flow.
  * **Phase B** — stamp + persist each document with NO long-held lock, using
    a per-document atomic lease (only one worker stamps a doc) and an
    ``attachment_id`` completion fence (a concurrent reclaim that loses the
    fence deletes its orphan object).
  * **Phase C** — once every document has an attachment, mint the download
    token, mark ``completed``, scrub PII. Owner + client e-mails and the
    contact timeline are POST-COMMIT side effects (never inside a txn — the
    e-mail send happens before the request commit otherwise).

The request session from ``get_db`` autobegins a transaction, so phases use
explicit ``await db.commit()`` (NOT ``async with db.begin()``, which would
raise "a transaction is already begun").
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import and_, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.attachments.service import AttachmentService
from src.onboarding import storage, tokens
from src.onboarding.completion_notices import (
    _download_url,
    notify_after_commit,
    resend_completion_notices,  # noqa: F401  (re-exported for router + tests)
)
from src.onboarding.models import OnboardingPacket, OnboardingPacketDocument
from src.onboarding.packet_errors import (
    PacketGoneError,
    PacketRaceError,
    PacketValidationError,
)
from src.onboarding.packet_service import (
    DEAD_STATUSES,
    DOWNLOAD_TOKEN_TTL,
    WRITABLE_STATUSES,
    PacketService,
    _ensure_aware,
    scrub_packet,
)
from src.onboarding.stamper import stamp_document
from src.onboarding.view_ledger import get_unviewed_packet_document_ids

logger = logging.getLogger(__name__)

# A stamp lease older than this is considered stale and reclaimable (a worker
# that died mid-stamp). Generous because to_thread stamping a large PDF is slow.
LEASE_TIMEOUT = timedelta(minutes=5)


def _now() -> datetime:
    return datetime.now(UTC)


async def complete_packet(
    db: AsyncSession,
    *,
    packet: OnboardingPacket,
    access_token: str,
    signer_email: str,
    signer_ip: str | None = None,
    signer_user_agent: str | None = None,
) -> dict:
    """Run the 3-phase completion. Returns ``{status, download_url?}``.

    Idempotent on ``completed`` (returns the existing state). Raises mapped
    packet errors (race→409, validation→422, gone→410) — the route wraps this
    in ``complete_errors_mapped``.
    """
    service = PacketService(db)

    # Idempotent / terminal short-circuits (matrix §5.2).
    if packet.status == "completed":
        return {"status": "completed", "download_url": _download_url(None)}
    if packet.status in DEAD_STATUSES:
        raise PacketGoneError("This onboarding link is no longer available.")
    if packet.status == "completing":
        raise PacketRaceError("This packet is already being finalized.")
    if packet.status == "completion_failed":
        raise PacketRaceError(
            "We're still finishing your documents; staff will retry."
        )

    await _phase_a_claim(
        db, packet=packet, access_token=access_token, signer_email=signer_email,
        signer_ip=signer_ip, signer_user_agent=signer_user_agent,
    )
    await _phase_b_stamp(db, packet_id=packet.id)
    raw_download = await _phase_c_finalize(db, packet_id=packet.id)

    # Reload for the TRUE durable status: completed (all docs attached),
    # completion_failed (Phase B infra error), or still completing (a concurrent
    # worker holds a lease and is finishing). Return the REAL status so the
    # client poll never contradicts the row.
    refreshed = await service.get_packet(packet.id)
    if refreshed is None:
        return {"status": "completion_failed"}
    if refreshed.status != "completed":
        return {"status": refreshed.status}

    await notify_after_commit(db, packet=refreshed, raw_download=raw_download)
    return {"status": "completed", "download_url": _download_url(raw_download)}


# --------------------------------------------------------------------------
# Phase A — claim under row lock
# --------------------------------------------------------------------------


async def _phase_a_claim(
    db: AsyncSession,
    *,
    packet: OnboardingPacket,
    access_token: str,
    signer_email: str,
    signer_ip: str | None = None,
    signer_user_agent: str | None = None,
) -> None:
    # Lock the packet + its docs. On Postgres these are real row locks; on
    # SQLite with_for_update is a silent no-op and correctness rests on the
    # conditional-UPDATE rowcount below.
    locked = await db.execute(
        select(OnboardingPacket)
        .where(OnboardingPacket.id == packet.id)
        .with_for_update()
    )
    p = locked.scalar_one()
    docs_result = await db.execute(
        select(OnboardingPacketDocument)
        .where(OnboardingPacketDocument.packet_id == p.id)
        .order_by(OnboardingPacketDocument.id)
        .with_for_update()
    )
    docs = list(docs_result.scalars().all())

    if p.status not in WRITABLE_STATUSES:
        # Capture status BEFORE rollback — rollback expires the ORM object, so a
        # later attribute read would lazy-load (→ MissingGreenlet on asyncpg).
        # This is the concurrent-/complete LOSER path: it must surface a clean
        # 409, not an opaque 500.
        status = p.status
        await db.rollback()
        if status in DEAD_STATUSES:
            raise PacketGoneError("This onboarding link is no longer available.")
        raise PacketRaceError(f"Packet is {status}; cannot complete.")

    # Signer identity must match the verified session's e-mail.
    if (signer_email or "").strip().lower() != (p.recipient_email or "").strip().lower():
        await db.rollback()
        raise PacketRaceError("Signer does not match this packet.")

    # Validate every doc fully (status unchanged on failure → 422, no
    # truncation). Roll back the FOR UPDATE txn before surfacing a 422 so the
    # row locks aren't held longer than the sibling guards above.
    try:
        _validate_documents_for_completion(docs)
        _assert_signature_present(p, docs)
        await _validate_documents_stampable(docs, p.signer_signature_image)
    except PacketValidationError:
        await db.rollback()
        raise
    await _assert_all_viewed(db, packet_id=p.id, access_token=access_token, docs=docs)

    sv = p.signature_version

    # Atomic conditional CLAIM. The doc-version fence is a correlated NOT
    # EXISTS: refuse if any doc's field_values_version drifted from what we
    # just read (a concurrent PATCH between the SELECT and here).
    version_subq = (
        select(OnboardingPacketDocument.id)
        .where(OnboardingPacketDocument.packet_id == p.id)
        .where(
            or_(
                *[
                    and_(
                        OnboardingPacketDocument.id == d.id,
                        OnboardingPacketDocument.field_values_version
                        != d.field_values_version,
                    )
                    for d in docs
                ]
            )
            if docs
            else False
        )
    )
    result = await db.execute(
        update(OnboardingPacket)
        .where(OnboardingPacket.id == p.id)
        .where(OnboardingPacket.status.in_(WRITABLE_STATUSES))
        .where(OnboardingPacket.signature_version == sv)
        .where(~version_subq.exists())
        .values(status="completing", completing_since=_now())
    )
    if result.rowcount == 0:
        await db.rollback()
        raise PacketRaceError(
            "The packet changed while finalizing; reload and retry."
        )
    # Record the e-sign audit trail on the claimed packet (persisted with the
    # claim commit): from where the signer submitted, and the consent timestamp
    # on each signature-bearing document. The disclosure snapshot names exactly
    # these fields, so they must actually be captured.
    p.signer_ip = signer_ip
    p.signer_user_agent = signer_user_agent
    consented = _now()
    for d in docs:
        if d.requires_esign and d.consented_at is None:
            d.consented_at = consented
    await db.commit()  # release the FOR UPDATE lock; PATCH/signature now 409


def _validate_documents_for_completion(docs: list[OnboardingPacketDocument]) -> None:
    """Every required field has a non-empty value; signature docs need a sig.

    Raises ``PacketValidationError`` (→ 422) — never truncates.
    """
    if not docs:
        raise PacketValidationError("Packet has no documents to complete.")
    for doc in docs:
        values = doc.field_values or {}
        for field in doc.field_definitions or []:
            if field.get("kind") == "signature":
                continue  # signature presence checked at packet level below
            if field.get("required"):
                fid = field.get("id")
                val = values.get(fid)
                if val is None or (isinstance(val, str) and not val.strip()):
                    raise PacketValidationError(
                        f"Required field '{field.get('label', fid)}' is empty."
                    )


async def _validate_documents_stampable(
    docs: list[OnboardingPacketDocument], signature_png: bytes | None
) -> None:
    """Dry-run the stamp of every document so content errors surface in Phase A.

    A bad date, a value that overflows its box, or an undecodable signature PNG
    raise ``ValueError`` in the stamper. Without this, that only happens in
    Phase B — AFTER the packet has flipped to ``completing`` — so the signer
    gets a dead-end ``completion_failed`` instead of a fixable 422. Running the
    same ``stamp_document`` path here (output discarded) catches those as a
    clean ``PacketValidationError`` (→ 422, status unchanged).

    Only content (``ValueError``) errors fail here; a storage read failure is
    infra (not the signer's fault), so it's skipped and left to Phase B's
    fail-closed handling.
    """
    for doc in docs:
        try:
            source = await storage.read_bytes(doc.pdf_path)
        except (FileNotFoundError, RuntimeError):
            continue
        try:
            await asyncio.to_thread(
                stamp_document, source, _fields_with_values(doc), signature_png
            )
        except ValueError as exc:
            raise PacketValidationError(str(exc)) from exc


def _assert_signature_present(
    packet: OnboardingPacket, docs: list[OnboardingPacketDocument]
) -> None:
    """A packet with any signature field (or any esign doc) must carry a drawn
    signature before completion.

    Without this gate, an unsigned esign packet would pass Phase A, flip to
    ``completing``, then have the stamper raise on the missing PNG in Phase B →
    the packet strands in ``completion_failed`` forever (the signature is still
    None). Catch it as a clean 422 with the status unchanged so the signer is
    simply told to sign.
    """
    needs_signature = any(
        doc.requires_esign
        or any(f.get("kind") == "signature" for f in (doc.field_definitions or []))
        for doc in docs
    )
    if needs_signature and packet.signer_signature_image is None:
        raise PacketValidationError("Please draw your signature before submitting.")


async def _assert_all_viewed(
    db: AsyncSession,
    *,
    packet_id: int,
    access_token: str,
    docs: list[OnboardingPacketDocument],
) -> None:
    unviewed = await get_unviewed_packet_document_ids(
        db, packet_id=packet_id, token=access_token
    )
    if unviewed:
        await db.rollback()
        raise PacketValidationError(
            "Open every document before submitting."
        )


# --------------------------------------------------------------------------
# Phase B — per-document atomic lease + stamp + fence
# --------------------------------------------------------------------------


async def _phase_b_stamp(db: AsyncSession, *, packet_id: int) -> None:
    service = PacketService(db)
    packet = await service.get_packet(packet_id)
    docs = await service.load_documents(packet_id)
    for doc in docs:
        if doc.attachment_id is not None:
            continue  # already stamped (a retry / concurrent worker)
        leased = await _acquire_lease(db, doc_id=doc.id)
        await db.commit()
        if not leased:
            continue  # another worker holds the lease or already attached

        # Stamp → attach → fence is one fail-closed unit: any failure (storage
        # /attach error, or a content error not caught by the Phase-A dry-run)
        # marks the packet completion_failed (staff retry) rather than stranding
        # it in `completing` or emitting a silently-wrong document. Content
        # errors (bad date/overflow/undecodable PNG) are now validated in Phase
        # A via _validate_documents_stampable, so a failure here is genuinely
        # infra/concurrency, not a client 422.
        try:
            stamped = await _stamp_one(doc, packet.signer_signature_image)
            att = await AttachmentService(db).create_from_bytes(
                content=stamped,
                original_filename=doc.original_filename,
                entity_type="contacts",
                entity_id=packet.contact_id,
                category="onboarding",
                uploaded_by=None,
                mime_type="application/pdf",
            )
            await db.flush()

            # Completion fence: only attach if still unattached (a concurrent
            # reclaim could have won). Loser deletes its orphan object + row.
            fenced = await db.execute(
                update(OnboardingPacketDocument)
                .where(OnboardingPacketDocument.id == doc.id)
                .where(OnboardingPacketDocument.attachment_id.is_(None))
                .values(attachment_id=att.id, completed_at=_now())
                .returning(OnboardingPacketDocument.id)
            )
            if fenced.first() is None:
                await storage.delete(att.file_path)
                await db.delete(att)
            await db.commit()
        except Exception as exc:
            # Fail-closed on ANY error — pypdf ``PyPdfError`` (corrupt source
            # copy), botocore ``ClientError`` (R2 write outage), storage
            # ``RuntimeError``, value/overflow — none of which subclass the old
            # narrow tuple. Mark completion_failed + release the lease + log,
            # never strand the packet `completing` behind an opaque 500.
            await _mark_failed(db, packet_id, str(exc))
            return


async def _acquire_lease(db: AsyncSession, *, doc_id: int) -> bool:
    """Atomically lease a doc for stamping; True iff this worker won it."""
    cutoff = _now() - LEASE_TIMEOUT
    result = await db.execute(
        update(OnboardingPacketDocument)
        .where(OnboardingPacketDocument.id == doc_id)
        .where(OnboardingPacketDocument.attachment_id.is_(None))
        .where(
            or_(
                OnboardingPacketDocument.stamp_lease_at.is_(None),
                OnboardingPacketDocument.stamp_lease_at < cutoff,
            )
        )
        .values(stamp_lease_at=_now())
        .returning(OnboardingPacketDocument.id)
    )
    return result.first() is not None


async def _stamp_one(
    doc: OnboardingPacketDocument, signature_png: bytes | None
) -> bytes:
    try:
        source = await storage.read_bytes(doc.pdf_path)
    except FileNotFoundError as exc:
        raise RuntimeError(f"Document PDF missing: {doc.id}") from exc
    fields = _fields_with_values(doc)
    return await asyncio.to_thread(stamp_document, source, fields, signature_png)


def _fields_with_values(doc: OnboardingPacketDocument) -> list[dict]:
    """Inject the saved field_values into each field-definition's ``value``.

    The stamper reads ``field["value"]`` for non-signature kinds; signature
    fields draw the packet's PNG (passed separately).
    """
    values = doc.field_values or {}
    out: list[dict] = []
    for field in doc.field_definitions or []:
        merged = dict(field)
        if field.get("kind") != "signature":
            merged["value"] = values.get(field.get("id"))
        out.append(merged)
    return out


async def _mark_failed(db: AsyncSession, packet_id: int, error: str) -> None:
    await db.rollback()
    await db.execute(
        update(OnboardingPacket)
        .where(OnboardingPacket.id == packet_id)
        .values(status="completion_failed")
    )
    await db.execute(
        update(OnboardingPacketDocument)
        .where(OnboardingPacketDocument.packet_id == packet_id)
        .where(OnboardingPacketDocument.attachment_id.is_(None))
        # Release the lease too, so a staff retry-completion can immediately
        # re-lease these docs instead of waiting out the LEASE_TIMEOUT the
        # just-set lease would otherwise impose.
        .values(filled_pdf_error=error[:1000], stamp_lease_at=None)
    )
    await db.commit()
    # logger.exception captures the active traceback (we're inside the Phase-B
    # except), so the real infra cause reaches Sentry, not just this summary.
    logger.exception("Onboarding packet %s completion failed: %s", packet_id, error)


# --------------------------------------------------------------------------
# Phase C — finalize (mint download token, scrub) — short txn
# --------------------------------------------------------------------------


async def _phase_c_finalize(db: AsyncSession, *, packet_id: int) -> str | None:
    service = PacketService(db)
    packet = await service.get_packet(packet_id)
    docs = await service.load_documents(packet_id)
    if packet is None or any(d.attachment_id is None for d in docs):
        return None  # not all attached — Phase B already marked failed

    raw_download = tokens.mint_token()
    packet.status = "completed"
    packet.completed_at = _now()
    packet.download_token_hash = tokens.hash_token(raw_download)
    packet.download_token_expires_at = _now() + DOWNLOAD_TOKEN_TTL
    # Scrub PII only AFTER the filled PDFs are confirmed attached (§12).
    scrub_packet(packet, docs)
    await db.commit()
    return raw_download


async def retry_completion(db: AsyncSession, *, packet: OnboardingPacket) -> dict:
    """Staff re-run of Phase B/C for a failed / stuck-completing packet.

    Idempotent via the per-doc lease + attachment_id fence. Refused once the
    packet has aged to ``abandoned`` (the recipient data is gone). A stuck
    ``completing`` packet is reclaimable only after its claim is stale.
    """
    if packet.status == "abandoned":
        raise PacketGoneError("Packet was abandoned; create a new one.")
    if packet.status == "completed":
        return {"status": "completed", "download_url": _download_url(None)}
    if packet.status not in ("completion_failed", "completing"):
        raise PacketRaceError(f"Packet is {packet.status}; nothing to retry.")
    if packet.status == "completing":
        # Only reclaim a genuinely stuck claim (worker died); a live claim is
        # still in flight and must not be double-driven.
        claimed_at = _ensure_aware(packet.completing_since) or _now()
        if claimed_at > _now() - LEASE_TIMEOUT:
            raise PacketRaceError("This packet is still being finalized.")

    # Re-mark completing so Phase B's leases apply uniformly, then drive B/C.
    await db.execute(
        update(OnboardingPacket)
        .where(OnboardingPacket.id == packet.id)
        .values(status="completing", completing_since=_now())
    )
    await db.commit()

    await _phase_b_stamp(db, packet_id=packet.id)
    raw_download = await _phase_c_finalize(db, packet_id=packet.id)

    service = PacketService(db)
    refreshed = await service.get_packet(packet.id)
    if refreshed is None:
        return {"status": "completion_failed"}
    if refreshed.status != "completed":
        return {"status": refreshed.status}
    await notify_after_commit(db, packet=refreshed, raw_download=raw_download)
    return {"status": "completed", "download_url": _download_url(raw_download)}
