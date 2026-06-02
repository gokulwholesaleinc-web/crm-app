"""Packet lifecycle service (Phase 2).

Create + freeze documents + resolve prefill; list (with the interim PII
sweep); get; revoke (scrub); per-document PATCH (version-guarded); signature
set (version-guarded); purge-pii; resend completion notice. The heavy
3-phase ``/complete`` orchestration lives in ``completion.py`` to keep this
module focused and under the per-file budget.

Status machine (see build-order §2):
    active → opened → in_progress → completing → completed
    (+ expired / revoked / completion_failed → abandoned terminal states)
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import overload

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.companies.models import Company
from src.contacts.models import Contact
from src.onboarding import storage, tokens
from src.onboarding.disclosure import (
    ONBOARDING_ESIGN_DISCLOSURE_VERSION,
    onboarding_esign_disclosure,
)
from src.onboarding.models import (
    OnboardingPacket,
    OnboardingPacketDocument,
    OnboardingTemplate,
)
from src.onboarding.packet_errors import (
    PacketGoneError,
    PacketInfraError,
    PacketRaceError,
    PacketValidationError,
)

# Statuses a recipient may still write to (view/patch/signature/complete).
WRITABLE_STATUSES = ("active", "opened", "in_progress")
# Terminal-dead states: public access returns 410 (data purged).
DEAD_STATUSES = ("expired", "revoked", "abandoned")

ACCESS_TOKEN_TTL = timedelta(days=30)
DOWNLOAD_TOKEN_TTL = timedelta(days=7)
# completion_failed ages to abandoned after this retention window (§7).
COMPLETION_FAILED_RETENTION = timedelta(days=7)

# Abuse caps (§6).
MAX_TEXT_VALUE_BYTES = 4 * 1024
MAX_FIELD_COUNT = 200


logger = logging.getLogger(__name__)


def _now() -> datetime:
    return datetime.now(UTC)


@overload
def _ensure_aware(value: datetime) -> datetime: ...
@overload
def _ensure_aware(value: None) -> None: ...
def _ensure_aware(value: datetime | None) -> datetime | None:
    """Treat a DB-loaded naive datetime as UTC before comparing against ``_now()``.

    ``DateTime(timezone=True)`` columns come back tz-aware from Postgres but
    NAIVE from SQLite (the test harness), and comparing a naive value against
    the aware ``_now()`` raises ``TypeError``. Mirrors the established
    ``audit/service.py::_ensure_aware`` / ``contracts/service.py`` pattern.
    ``None`` passes through unchanged. The overloads preserve non-null-ness so a
    guarded ``_ensure_aware(col) <= _now()`` doesn't trip pyright's
    reportOptionalOperand.
    """
    if value is not None and value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


def _mask_email(email: str | None) -> str:
    """``alice@example.com`` → ``a***@example.com`` (staff list, no full PII)."""
    if not email or "@" not in email:
        return "***"
    local, _, domain = email.partition("@")
    head = local[0] if local else ""
    return f"{head}***@{domain}"


def scrub_packet(packet: OnboardingPacket, documents: list[OnboardingPacketDocument]) -> None:
    """Null recipient field values + the drawn signature (PII scrub, §12)."""
    packet.signer_signature_image = None
    for doc in documents:
        doc.field_values = {}


class PacketService:
    def __init__(self, db: AsyncSession):
        self.db = db

    # ------------------------------------------------------------------
    # Loaders
    # ------------------------------------------------------------------

    async def get_packet(self, packet_id: int) -> OnboardingPacket | None:
        result = await self.db.execute(
            select(OnboardingPacket).where(OnboardingPacket.id == packet_id)
        )
        return result.scalar_one_or_none()

    async def load_documents(self, packet_id: int) -> list[OnboardingPacketDocument]:
        result = await self.db.execute(
            select(OnboardingPacketDocument)
            .where(OnboardingPacketDocument.packet_id == packet_id)
            .order_by(
                OnboardingPacketDocument.display_order,
                OnboardingPacketDocument.id,
            )
        )
        return list(result.scalars().all())

    async def get_by_token_hash(self, token_hash: str) -> OnboardingPacket | None:
        result = await self.db.execute(
            select(OnboardingPacket).where(
                OnboardingPacket.token_hash == token_hash
            )
        )
        return result.scalar_one_or_none()

    async def resolve_company_name(self, packet: OnboardingPacket) -> str:
        """Name shown in the disclosure — linked company, else neutral label."""
        if packet.company_id is not None:
            result = await self.db.execute(
                select(Company.name).where(Company.id == packet.company_id)
            )
            name = result.scalar_one_or_none()
            if name:
                return name
        return "your provider"

    # ------------------------------------------------------------------
    # Create
    # ------------------------------------------------------------------

    async def create_packet(
        self,
        *,
        created_by_id: int | None,
        contact_id: int,
        recipient_email: str,
        template_ids: list[int],
        recipient_name: str | None = None,
        company_id: int | None = None,
        proposal_id: int | None = None,
        requires_esign_override: bool | None = None,
    ) -> tuple[OnboardingPacket, str]:
        """Create a packet + one frozen document per active template.

        Returns ``(packet, raw_access_token)`` — the raw token is surfaced
        exactly once by the caller as ``access_url`` and never stored.
        """
        templates = await self._load_active_templates(template_ids)

        raw_token = tokens.mint_token()
        packet = OnboardingPacket(
            contact_id=contact_id,
            company_id=company_id,
            proposal_id=proposal_id,
            recipient_email=recipient_email,
            recipient_name=recipient_name,
            token_hash=tokens.hash_token(raw_token),
            token_expires_at=_now() + ACCESS_TOKEN_TTL,
            status="active",
            created_by_id=created_by_id,
        )
        self.db.add(packet)
        await self.db.flush()  # assign packet.id

        prefill = await self._resolve_prefill_values(contact_id, company_id)
        for order, template in enumerate(templates):
            requires_esign = (
                requires_esign_override
                if requires_esign_override is not None
                else template.requires_esign
            )
            field_defs = list(template.field_definitions or [])
            self._assert_esign_signature_consistency(
                template.id, requires_esign, field_defs
            )
            pdf_path = await self._copy_template_pdf(template, packet.id)
            doc = OnboardingPacketDocument(
                packet_id=packet.id,
                display_order=order,
                source_template_id=template.id,
                original_filename=f"{template.name}.pdf",
                pdf_path=pdf_path,
                field_definitions=field_defs,
                field_values=self._seed_prefill(field_defs, prefill),
                requires_esign=requires_esign,
            )
            if requires_esign:
                doc.esign_disclosure_version = ONBOARDING_ESIGN_DISCLOSURE_VERSION
                doc.esign_disclosure_snapshot = onboarding_esign_disclosure(
                    company_name=await self.resolve_company_name(packet)
                )
            self.db.add(doc)
        await self.db.flush()
        return packet, raw_token

    async def _load_active_templates(
        self, template_ids: list[int]
    ) -> list[OnboardingTemplate]:
        result = await self.db.execute(
            select(OnboardingTemplate).where(
                OnboardingTemplate.id.in_(template_ids)
            )
        )
        by_id = {t.id: t for t in result.scalars().all()}
        ordered: list[OnboardingTemplate] = []
        for tid in template_ids:
            template = by_id.get(tid)
            if template is None:
                raise PacketValidationError(f"Template {tid} not found")
            if not template.is_active:
                raise PacketValidationError(
                    f"Template {tid} is retired and cannot be sent"
                )
            if not template.pdf_path:
                raise PacketValidationError(
                    f"Template {tid} has no PDF uploaded yet"
                )
            ordered.append(template)
        return ordered

    async def _copy_template_pdf(
        self, template: OnboardingTemplate, packet_id: int
    ) -> str:
        """Copy the template PDF into a per-packet object and return its ref."""
        try:
            source = await storage.read_bytes(template.pdf_path)
        except FileNotFoundError as exc:
            raise PacketValidationError(
                f"Template {template.id} PDF is missing from storage"
            ) from exc
        except RuntimeError as exc:
            raise PacketInfraError("PDF storage is unavailable") from exc
        key = f"onboarding_packets/{packet_id}/{uuid.uuid4().hex}.pdf"
        try:
            return await storage.write(key, source, "application/pdf")
        except RuntimeError as exc:
            raise PacketInfraError("Could not store the packet PDF copy") from exc

    async def _resolve_prefill_values(
        self, contact_id: int, company_id: int | None
    ) -> dict[str, str]:
        """Resolve the allowed prefill keys (contact.name / company.name).

        Only the safe-to-echo identity fields — never contact.email.
        """
        values: dict[str, str] = {}
        result = await self.db.execute(
            select(Contact).where(Contact.id == contact_id)
        )
        contact = result.scalar_one_or_none()
        if contact is not None:
            values["contact.name"] = (
                f"{contact.first_name} {contact.last_name}".strip()
            )
        if company_id is not None:
            cresult = await self.db.execute(
                select(Company.name).where(Company.id == company_id)
            )
            cname = cresult.scalar_one_or_none()
            if cname:
                values["company.name"] = cname
        return values

    @staticmethod
    def _assert_esign_signature_consistency(
        template_id: int, requires_esign: bool, field_defs: list[dict]
    ) -> None:
        """Reject a packet document whose e-sign flag and signature field disagree.

        Invariant #10, enforced in BOTH directions at send time (the template
        guard only enforces esign→signature):

          * ``requires_esign`` with NO signature field — forced via
            ``requires_esign_override`` on a sig-less template — can never
            collect a signature, yet the signer is asked to consent and draw
            one; the stamper draws nothing, producing an invisibly-"signed" PDF.
          * a signature field on a NON-esign doc never shows the signature pad
            on the fill page (it gates on ``requires_esign``), so completion is
            blocked forever waiting for a signature the recipient can't provide.

        Either mismatch is a fail-closed 422 (``PacketValidationError``) rather
        than a silently broken or uncompletable packet.
        """
        has_signature_field = any(
            (f.get("kind") if isinstance(f, dict) else None) == "signature"
            for f in field_defs
        )
        if requires_esign and not has_signature_field:
            raise PacketValidationError(
                f"Template {template_id} requires e-sign but has no signature "
                "field; it cannot collect a signature."
            )
        if has_signature_field and not requires_esign:
            raise PacketValidationError(
                f"Template {template_id} has a signature field, so e-sign "
                "cannot be disabled for it."
            )

    @staticmethod
    def _seed_prefill(
        field_defs: list[dict], prefill: dict[str, str]
    ) -> dict[str, str]:
        """Pre-populate field_values for fields carrying a known prefill key."""
        seeded: dict[str, str] = {}
        for field in field_defs:
            key = field.get("prefill")
            fid = field.get("id")
            if key and fid and key in prefill:
                seeded[fid] = prefill[key]
        return seeded

    # ------------------------------------------------------------------
    # List (+ interim PII sweep) / revoke / purge
    # ------------------------------------------------------------------

    async def list_packets(self, contact_id: int) -> list[OnboardingPacket]:
        """List a contact's packets, lazily expiring/aging stale ones (§7)."""
        result = await self.db.execute(
            select(OnboardingPacket)
            .where(OnboardingPacket.contact_id == contact_id)
            .order_by(OnboardingPacket.created_at.desc())
        )
        packets = list(result.scalars().all())
        for packet in packets:
            # Isolate each packet's sweep: one bad row must not 500 the whole
            # list AND must not leave the other stale packets' PII unscrubbed.
            try:
                await self._sweep_packet(packet)
            except Exception:
                logger.exception(
                    "Onboarding list-time sweep failed for packet %s", packet.id
                )
        return packets

    async def _sweep_packet(self, packet: OnboardingPacket) -> None:
        """Interim list-time sweep: flip+scrub expired, age completion_failed."""
        now = _now()
        if packet.status in WRITABLE_STATUSES + ("completion_failed",):
            if (
                packet.token_expires_at is not None
                and _ensure_aware(packet.token_expires_at) <= now
            ):
                packet.status = "expired"
                scrub_packet(packet, await self.load_documents(packet.id))
                packet.token_hash = self._dead_token_hash(packet.id)
                return
        if packet.status == "completion_failed":
            failed_at = _ensure_aware(packet.completing_since or packet.updated_at)
            if failed_at and failed_at <= now - COMPLETION_FAILED_RETENTION:
                packet.status = "abandoned"
                packet.abandoned_at = now
                scrub_packet(packet, await self.load_documents(packet.id))

    @staticmethod
    def _dead_token_hash(packet_id: int) -> str:
        """A non-null, unusable placeholder so the unique token_hash NOT-NULL
        column stays satisfied after a token is killed (no raw token hashes to
        it; lookups by a real token can never match)."""
        return f"dead:{packet_id}:{uuid.uuid4().hex}"

    async def revoke_packet(
        self, packet: OnboardingPacket, *, revoked_by_id: int | None
    ) -> OnboardingPacket:
        if packet.status in DEAD_STATUSES + ("completed",):
            raise PacketRaceError(
                f"Packet is already {packet.status}; cannot revoke."
            )
        documents = await self.load_documents(packet.id)
        old_hash = packet.token_hash
        packet.status = "revoked"
        packet.revoked_at = _now()
        packet.revoked_by_id = revoked_by_id
        packet.token_hash = self._dead_token_hash(packet.id)
        packet.download_token_hash = None
        packet.download_token_expires_at = None
        scrub_packet(packet, documents)
        tokens.reset_throttle(old_hash)
        await self.db.flush()
        return packet

    # Statuses for which a staff "resend invite" is allowed (§5.1). A live
    # packet just re-mints the link; an ``expired`` one restarts fresh.
    RESEND_ALLOWED = WRITABLE_STATUSES + ("expired",)

    async def resend_invite(
        self, packet: OnboardingPacket, *, actor_id: int | None
    ) -> str:
        """Mint a FRESH access token + reset expiry; return the raw token.

        Allowed for ``active | opened | in_progress | expired``; refused for
        ``completed | revoked | completing | abandoned`` (409 → staff should
        retry/resend completion instead). An ``expired`` packet flips back to
        ``active`` (its old token was scrubbed by the list-time sweep). The
        old token's verify throttle is reset (like ``revoke_packet``). Flushes
        only — the route/caller COMMITS before queuing the invite e-mail
        (``queue_email`` may send synchronously), so the new token is durable
        before its link is sent.
        """
        if packet.status not in self.RESEND_ALLOWED:
            raise PacketRaceError(
                f"Packet is {packet.status}; the onboarding invite can't be resent."
            )
        old_hash = packet.token_hash
        raw_token = tokens.mint_token()
        packet.token_hash = tokens.hash_token(raw_token)
        packet.token_expires_at = _now() + ACCESS_TOKEN_TTL
        if packet.status == "expired":
            packet.status = "active"
        packet.updated_by_id = actor_id
        tokens.reset_throttle(old_hash)
        await self.db.flush()
        return raw_token

    async def purge_pii(self, packet: OnboardingPacket) -> OnboardingPacket:
        """Staff manual scrub — null values + signature, status unchanged."""
        documents = await self.load_documents(packet.id)
        scrub_packet(packet, documents)
        await self.db.flush()
        return packet

    # ------------------------------------------------------------------
    # Public document mutations (version-guarded)
    # ------------------------------------------------------------------

    def _assert_public_writable(self, packet: OnboardingPacket) -> None:
        if packet.status in DEAD_STATUSES:
            raise PacketGoneError("This onboarding link is no longer available.")
        if packet.status not in WRITABLE_STATUSES:
            # completing / completed / completion_failed → 409 (read-only).
            raise PacketRaceError(
                f"Packet is {packet.status}; documents can't be edited."
            )

    async def patch_document(
        self,
        packet: OnboardingPacket,
        doc: OnboardingPacketDocument,
        *,
        field_values: dict,
        base_version: int,
    ) -> int:
        """Merge field_values into a document; 409 on version drift.

        The check-and-bump is a single conditional ``UPDATE ... WHERE
        field_values_version = base_version`` whose ``rowcount`` is the fence —
        two concurrent saves that both read version N can't both win (the
        loser matches 0 rows → 409). A read-compare-then-increment under READ
        COMMITTED would lose-update silently.
        """
        self._assert_public_writable(packet)
        self._validate_field_values(doc, field_values)
        merged = dict(doc.field_values or {})
        merged.update(field_values)
        # Advance active/opened → in_progress atomically, BEFORE the document
        # write. Two reasons: (1) lock order — Phase A's completion claim locks
        # the packet THEN its documents, so taking the packet write first here
        # keeps both paths packet→document and avoids a deadlock; (2) it can't
        # clobber a claim — the conditional WHERE only matches active/opened, so
        # once a concurrent /complete has flipped the packet to ``completing``
        # this is a no-op (0 rows) rather than a stale in-memory write resetting
        # the status to in_progress. ``synchronize_session=False`` leaves the
        # in-memory object untouched (the route returns the version, not status).
        await self.db.execute(
            update(OnboardingPacket)
            .where(OnboardingPacket.id == packet.id)
            .where(OnboardingPacket.status.in_(("active", "opened")))
            .values(status="in_progress")
            .execution_options(synchronize_session=False)
        )
        result = await self.db.execute(
            update(OnboardingPacketDocument)
            .where(OnboardingPacketDocument.id == doc.id)
            .where(OnboardingPacketDocument.field_values_version == base_version)
            # Packet-writable fence: refuse the write once a /complete claim has
            # flipped the packet out of a writable status AFTER this request
            # loaded it. The version fence alone is insufficient — completion
            # does NOT bump field_values_version, so without this a stale save
            # could land after the claim and mutate the very field_values Phase
            # B is about to stamp.
            .where(
                select(OnboardingPacket.id)
                .where(OnboardingPacket.id == packet.id)
                .where(OnboardingPacket.status.in_(WRITABLE_STATUSES))
                .exists()
            )
            .values(field_values=merged, field_values_version=base_version + 1)
            # synchronize_session="fetch": pre-select the PKs matching the FULL
            # WHERE (including the packet-writable fence) before updating, so the
            # in-memory ``doc`` is only synced when the DB row actually matched.
            # The default 'evaluate' would set the new values on the stale ORM
            # object on the REJECT path (it can't see the committed claim),
            # leaving a phantom; 'fetch' reflects the real 0-row outcome while
            # still keeping the object correct on success.
            .execution_options(synchronize_session="fetch")
            .returning(OnboardingPacketDocument.field_values_version)
        )
        row = result.first()
        if row is None:
            raise PacketRaceError(
                "This document changed since you loaded it; reload and retry."
            )
        await self.db.flush()
        return row[0]

    @staticmethod
    def _validate_field_values(doc: OnboardingPacketDocument, values: dict) -> None:
        if not isinstance(values, dict):
            raise PacketValidationError("field_values must be an object")
        if len(values) > MAX_FIELD_COUNT:
            raise PacketValidationError("Too many fields in one update")
        known_ids = {
            f.get("id") for f in (doc.field_definitions or []) if f.get("id")
        }
        for fid, val in values.items():
            if fid not in known_ids:
                raise PacketValidationError(f"Unknown field '{fid}'")
            # Field values are strings only (the wire contract is
            # Record<string, string>). A stored bool/int/float would round-trip
            # to the public page and crash its ``.trim()`` / controlled-input
            # render, and mis-stamps as ``str(value)``. Reject non-strings (None
            # is allowed to clear a field).
            if val is not None and not isinstance(val, str):
                raise PacketValidationError(f"Field '{fid}' has an invalid value")
            if isinstance(val, str) and len(val.encode("utf-8")) > MAX_TEXT_VALUE_BYTES:
                raise PacketValidationError(f"Field '{fid}' value is too long")

    async def record_consent(
        self,
        packet: OnboardingPacket,
        *,
        disclosure_version: str | None = None,
    ) -> int:
        """Record electronic-records consent per e-sign document (§D.1).

        Affirmative consent step, distinct from the signature: sets
        ``consented_at = now()`` on every ``requires_esign`` doc whose
        ``consented_at`` is still NULL. Idempotent (already-consented docs are
        left untouched). Returns the number of docs newly consented (0 if all
        were already consented or there are no e-sign docs).

        Belt-and-suspenders version echo: the served disclosure text + version
        are snapshotted at create time and never change, so if the client
        echoes ``disclosure_version`` it MUST equal the stored snapshot version
        — a mismatch means the client saw stale text (e.g. across a re-send),
        which is a 409 (``PacketRaceError``) rather than recording consent to
        text the signer didn't actually see.
        """
        self._assert_public_writable(packet)
        docs = await self.load_documents(packet.id)
        esign_docs = [d for d in docs if d.requires_esign]
        if disclosure_version is not None:
            for doc in esign_docs:
                if (
                    doc.esign_disclosure_version is not None
                    and doc.esign_disclosure_version != disclosure_version
                ):
                    raise PacketRaceError(
                        "The consent disclosure changed since you loaded it; "
                        "reload and review it again."
                    )
        now = _now()
        consented = 0
        for doc in esign_docs:
            if doc.consented_at is None:
                doc.consented_at = now
                consented += 1
        await self.db.flush()
        return consented

    async def set_signature(
        self,
        packet: OnboardingPacket,
        *,
        signature_png: bytes,
        base_signature_version: int,
    ) -> int:
        """Store the drawn signature PNG; 409 on signature_version drift.

        Same atomic fence as ``patch_document`` — a conditional ``UPDATE ...
        WHERE signature_version = base_signature_version`` so two concurrent
        signature saves can't both bump from the same base (lost update).
        """
        self._assert_public_writable(packet)
        result = await self.db.execute(
            update(OnboardingPacket)
            .where(OnboardingPacket.id == packet.id)
            .where(OnboardingPacket.signature_version == base_signature_version)
            # Packet-writable fence: a /complete claim flips the packet to
            # ``completing`` and the recipient must not be able to overwrite the
            # signature Phase B is stamping. The signature_version alone doesn't
            # protect this — completion doesn't bump it — so gate on the status
            # too. This UPDATE also serializes behind Phase A's FOR UPDATE on the
            # packet row, so it sees the committed post-claim status.
            .where(OnboardingPacket.status.in_(WRITABLE_STATUSES))
            .values(
                signer_signature_image=signature_png,
                signature_version=base_signature_version + 1,
            )
            # synchronize_session="fetch": pre-select the matching PK using the
            # FULL WHERE (including the status fence) before updating, so the
            # in-memory packet is synced ONLY when the DB row actually matched.
            # The default 'evaluate' reads the request's stale (pre-claim) status
            # and would set signature_version on the in-memory object even on the
            # REJECT path where the DB matched 0 rows, leaving a phantom; 'fetch'
            # reflects the real outcome and still keeps the object correct on a
            # successful save (the shared test session reads the same instance).
            .execution_options(synchronize_session="fetch")
            .returning(OnboardingPacket.signature_version)
        )
        row = result.first()
        if row is None:
            raise PacketRaceError(
                "Signature changed since you loaded it; reload and retry."
            )
        # Running the UPDATE through ``session.execute`` synchronizes the
        # in-memory ``packet`` (not left dirty), so the fence isn't clobbered by
        # a later flush. Completion also re-reads the row under a FOR UPDATE lock.
        return row[0]
