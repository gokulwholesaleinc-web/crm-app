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
from src.onboarding.kinds import get_handler
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
    ensure_pdf_suffix,
    scrub_packet,
)
from src.onboarding.service import has_signature_field
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
        await _validate_documents_for_completion(db, docs)
        _assert_consent_recorded(docs)
        _assert_signature_present(p, docs)
        await _validate_documents_stampable(db, docs, p, p.signer_signature_image)
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
    # claim commit): from where the signer submitted. Consent (``consented_at``)
    # is now its own affirmative step recorded by ``POST /consent`` BEFORE
    # submit (gated above by ``_assert_consent_recorded``), not an implicit
    # side effect of claiming here (§D.2).
    p.signer_ip = signer_ip
    p.signer_user_agent = signer_user_agent
    await db.commit()  # release the FOR UPDATE lock; PATCH/signature now 409


async def _validate_documents_for_completion(
    db: AsyncSession, docs: list[OnboardingPacketDocument]
) -> None:
    """Every required field has a non-empty value; signature docs need a sig.

    Loads, per doc, the ``onboarding_packet_uploads`` rows + the set of
    ``field_id``s that have a stored ``onboarding_secret_values`` ciphertext, and
    passes them to the kind handler's ``required_satisfied`` (P0-1/P0-8) — so
    ``upload_request`` counts real files and a sensitive text field counts a
    stored secret rather than a (deliberately absent) ``field_values`` entry.
    Raises ``PacketValidationError`` (→ 422) — never truncates.

    Runs inside Phase A's FOR-UPDATE txn (before the claim); the reads here are
    on child tables of the already-locked documents, so they add no new lock.
    """
    from src.onboarding.models import (
        OnboardingPacketUpload,
        OnboardingSecretValue,
    )

    if not docs:
        raise PacketValidationError("Packet has no documents to complete.")
    for doc in docs:
        handler = get_handler(doc.kind)
        values = doc.field_values or {}
        uploads = list(
            (
                await db.execute(
                    select(OnboardingPacketUpload).where(
                        OnboardingPacketUpload.packet_document_id == doc.id
                    )
                )
            )
            .scalars()
            .all()
        )
        # A ``dict`` (field_id → True) matches the handler Protocol's
        # ``secrets: dict | None`` and lets a kind handler test membership for a
        # sensitive field with a present stored ciphertext.
        secret_field_ids = {
            row: True
            for row in (
                await db.execute(
                    select(OnboardingSecretValue.field_id).where(
                        OnboardingSecretValue.packet_document_id == doc.id
                    )
                )
            )
            .scalars()
            .all()
        }
        for field in doc.field_definitions or []:
            # Per-field required-check delegated to the kind handler (P0-1/P0-8):
            # esign = non-empty string; questionnaire = non-empty str/list +
            # conditional Other write-in (+ a stored secret for a sensitive
            # field); upload = real upload-row count. Signature presence stays a
            # packet-level check (``_assert_signature_present``), which the
            # handler returns True for so it doesn't double-raise here.
            if not handler.required_satisfied(
                field, values, uploads, secret_field_ids
            ):
                raise PacketValidationError(
                    f"Required field "
                    f"'{field.get('label', field.get('id'))}' is empty."
                )


async def _validate_documents_stampable(
    db: AsyncSession,
    docs: list[OnboardingPacketDocument],
    packet: OnboardingPacket,
    signature_png: bytes | None,
) -> None:
    """Dry-run each document's artifact so content errors surface in Phase A.

    Kind-aware via ``produce_artifact(dry_run=True)``: the esign stamper, the
    questionnaire Platypus summary, and the upload manifest each run their real
    producibility path with the output discarded. A bad date / box overflow /
    undecodable signature PNG / Platypus overflow raises ``ValueError`` or
    ``OSError`` → a clean ``PacketValidationError`` (→ 422, status unchanged).
    Without this, that error would only hit Phase B — AFTER the packet flips to
    ``completing`` — stranding the signer in a dead-end ``completion_failed``.

    Only CONTENT errors fail here; a storage read failure is infra (not the
    signer's fault) and is normalized to ``RuntimeError`` by ``read_bytes`` (or
    ``FileNotFoundError`` for a missing copy), so those are skipped — any
    ``OSError`` reaching the producer is a decode failure of the signer's own
    input, not storage.
    """
    for doc in docs:
        handler = get_handler(doc.kind)
        try:
            await handler.produce_artifact(
                db,
                doc=doc,
                packet=packet,
                signature_png=signature_png,
                dry_run=True,
            )
        except (FileNotFoundError, RuntimeError):
            continue  # infra (storage read / missing copy) — not a content 422
        except (ValueError, OSError) as exc:
            raise PacketValidationError(str(exc)) from exc


def _assert_consent_recorded(docs: list[OnboardingPacketDocument]) -> None:
    """Every e-sign doc must have ``consented_at`` set before completion (§D.2).

    Consent is a deliberate affirmative step (``POST /consent``) recorded
    BEFORE submit — ESIGN best practice — not an implicit side effect of
    clicking Submit. A missing-consent ``/complete`` is a clean 422 with the
    packet status unchanged (raised inside Phase A's pre-claim try-block, so
    no claim happens).
    """
    for doc in docs:
        if doc.requires_esign and doc.consented_at is None:
            raise PacketValidationError(
                "Please review and accept the electronic-records consent "
                "before submitting."
            )


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

    H1 (signature-aware, closes in-flight packets): an ``esign_pdf`` doc that
    carries a PDF is a signing ceremony regardless of its (possibly pre-fix)
    ``requires_esign`` flag. Completing one with NO signature field would flatten
    and attach an UNSIGNED "completed" PDF — no signature was ever collected. The
    send guard (``template_send_status``) now rejects this state at create time,
    but a packet snapshotted BEFORE that guard shipped can still reach here, so
    require a signature field on every esign-with-PDF doc and reject as a clean
    422 (status unchanged) when one is missing.
    """
    for doc in docs:
        if (
            doc.kind == "esign_pdf"
            and doc.pdf_path
            and not has_signature_field(doc.field_definitions)
        ):
            raise PacketValidationError(
                "This e-sign document has no signature field and cannot be signed."
            )
    # Every esign-with-PDF doc that survived the loop above HAS a signature field,
    # so the signature-field clause already covers it — no separate esign_pdf
    # clause is needed here.
    needs_signature = any(
        doc.requires_esign or has_signature_field(doc.field_definitions)
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
    # Fail closed if the packet vanished OR left the ``completing`` state under
    # this worker: a concurrent list-sweep can flip a stale packet to
    # ``abandoned`` and PURGE it (deleting the upload files + secret rows)
    # between Phase A's claim-commit and this reload. Without this guard Phase B
    # would then stamp a manifest/summary from emptied field_values / deleted
    # uploads and attach a silently-wrong (empty) artifact on a dead packet.
    if packet is None or packet.status != "completing":
        return
    docs = await service.load_documents(packet_id)
    # H1 choke point (shared by both completion drivers). _assert_signature_present
    # blocks the public /complete path in Phase A, but the staff ``retry_completion``
    # path re-marks ``completing`` and calls this function DIRECTLY (skipping Phase
    # A), so a packet snapshotted in completion_failed BEFORE the signature-aware
    # guard shipped could otherwise be stamped here into a flattened, UNSIGNED PDF.
    # An esign_pdf doc with a PDF but no signature field can never be signed — fail
    # closed into completion_failed rather than emit an unsigned "completed" artifact.
    for doc in docs:
        if (
            doc.kind == "esign_pdf"
            and doc.pdf_path
            and not has_signature_field(doc.field_definitions)
        ):
            await _mark_failed(
                db,
                packet_id,
                "esign_pdf document has no signature field; refusing to stamp "
                "an unsigned PDF.",
            )
            return
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
            handler = get_handler(doc.kind)
            stamped = await handler.produce_artifact(
                db,
                doc=doc,
                packet=packet,
                signature_png=packet.signer_signature_image,
                dry_run=False,
            )
            if stamped is None:
                # None of the v3 kinds return None (esign stamps, questionnaire
                # renders a summary, upload renders a manifest). A future
                # no-artifact kind would need its own done-fence; fail closed
                # rather than silently leave the doc unattached.
                raise RuntimeError(
                    f"Document {doc.id} kind {doc.kind!r} produced no artifact"
                )
            att = await AttachmentService(db).create_from_bytes(
                content=stamped,
                # The artifact is always a PDF (esign stamp / questionnaire
                # summary / upload manifest); the saved attachment name carries
                # ``.pdf`` even for form kinds whose title has none (F2 — the
                # doc title itself stays clean on the fill page).
                original_filename=ensure_pdf_suffix(doc.original_filename),
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
            await _mark_failed(db, packet_id, str(exc), exc_info=True)
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


async def _mark_failed(
    db: AsyncSession, packet_id: int, error: str, *, exc_info: bool = False
) -> None:
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
    # Only attach a traceback when an exception is actually active (the Phase-B
    # stamp except). The H1 signature choke point calls this on a deliberate,
    # non-exception rejection — ``logger.exception`` there would log a bogus
    # ``NoneType: None`` traceback to Sentry, so the caller passes exc_info=False.
    logger.error(
        "Onboarding packet %s completion failed: %s",
        packet_id,
        error,
        exc_info=exc_info,
    )


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
    # purge=False RETAINS the delivered collected data — upload files (gov-ID /
    # brand assets), secret ciphertext (F4 passwords), and questionnaire answers
    # are the deliverable Lorenzo accesses; only the signature + esign answers
    # (already in the stamped PDF) are scrubbed. The full PII purge is reserved
    # for non-delivery terminals (revoke / expire / abandon / purge_pii).
    await scrub_packet(db, packet, docs, purge=False)
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

    # Capture the PK as a plain int before driving the phases: Phase B's
    # ``_mark_failed`` (or any commit inside _phase_b_stamp) expires the ORM
    # ``packet`` (expire_on_commit), so a later ``packet.id`` would trigger a sync
    # lazy-load → MissingGreenlet on the async session. The status guards above
    # still read the (fresh) in-memory packet.
    packet_id = packet.id

    # Re-mark completing so Phase B's leases apply uniformly, then drive B/C.
    await db.execute(
        update(OnboardingPacket)
        .where(OnboardingPacket.id == packet_id)
        .values(status="completing", completing_since=_now())
    )
    await db.commit()

    await _phase_b_stamp(db, packet_id=packet_id)
    raw_download = await _phase_c_finalize(db, packet_id=packet_id)

    service = PacketService(db)
    refreshed = await service.get_packet(packet_id)
    if refreshed is None:
        return {"status": "completion_failed"}
    if refreshed.status != "completed":
        return {"status": refreshed.status}
    await notify_after_commit(db, packet=refreshed, raw_download=raw_download)
    return {"status": "completed", "download_url": _download_url(raw_download)}
