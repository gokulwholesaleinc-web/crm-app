"""Client Onboarding template + packet models.

Phase 1 holds the team-library template row: a staff-uploaded PDF plus the
field-definition overlay that the per-field stamper burns into the document.
Phase 2 adds the per-recipient *packet* (a token-gated copy of one or more
templates the client fills + e-signs from a public link) and its per-document
copies + view ledger. See CLIENT_ONBOARDING_PLAN.md §14 Phase 1/2 and the
build-order note.
"""

from datetime import datetime

import sqlalchemy as sa
from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    PrimaryKeyConstraint,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import TypeDecorator

from src.core.mixins.auditable import AuditableMixin
from src.database import Base


class _FieldDefinitions(TypeDecorator):
    """JSONB on Postgres, JSON on SQLite (test DB).

    Module-local clone of ``proposals/models.py:_SignatureCoords`` so the
    onboarding module stays self-contained (no cross-feature import).
    Stores the field-definition array (see schemas.FieldDefinition).
    """

    impl = JSON
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(JSONB())
        return dialect.type_descriptor(JSON())


class OnboardingTemplate(Base, AuditableMixin):
    """A reusable onboarding PDF + its field-definition overlay.

    ``AuditableMixin`` supplies ``created_at``/``updated_at``/
    ``created_by_id``/``updated_by_id`` — they are NOT redeclared here.
    """

    __tablename__ = "onboarding_templates"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    # null = universal template; controlled slug otherwise (validated in service).
    service_tag: Mapped[str | None] = mapped_column(String(100), index=True)
    owner_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        index=True,
    )
    # Storage ref ("obj://<key>" for R2 or a path relative to uploads/ for
    # disk). Null until the first /pdf upload — field_definitions cannot be
    # saved while this is null (bounds-validation needs the page count).
    pdf_path: Mapped[str | None] = mapped_column(Text)
    pdf_version: Mapped[int] = mapped_column(
        Integer, default=1, server_default="1", nullable=False
    )
    field_definitions: Mapped[list[dict]] = mapped_column(
        _FieldDefinitions,
        nullable=False,
        default=list,
        server_default="[]",
    )
    requires_esign: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=sa.false(), nullable=False
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=sa.true(), nullable=False
    )
    # v3 polymorphic-document discriminator. Existing rows backfill to the
    # e-sign kind (migration 052). The CHECK keeps prod + create_all (SQLite)
    # in lock-step on the allowed set.
    kind: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="esign_pdf",
        server_default="esign_pdf",
    )

    __table_args__ = (
        CheckConstraint(
            "kind IN ('esign_pdf', 'questionnaire', 'upload_request')",
            name="ck_onboarding_templates_kind",
        ),
        # The seed UPSERTs by ``name`` and the editor disambiguates templates by
        # it — a DB-level unique backstops the application-only name keying so an
        # admin-created same-name row can't be silently clobbered or double-sent
        # (migration 054; create_all keeps SQLite tests in lock-step). S1.
        UniqueConstraint("name", name="uq_onboarding_templates_name"),
    )


# --------------------------------------------------------------------------
# Phase 2 — packets
# --------------------------------------------------------------------------


class OnboardingPacket(Base, AuditableMixin):
    """A token-gated bundle of onboarding documents sent to one recipient.

    Created from one or more active templates; each selected template is
    frozen into an ``OnboardingPacketDocument`` (its own PDF copy + field
    snapshot) so later template edits can't mutate a packet in flight.

    The raw access token is NEVER stored — only ``token_hash`` (sha256). The
    raw token is surfaced exactly once in the ``POST /packets`` response and
    is otherwise unrecoverable. ``AuditableMixin`` supplies
    ``created_at``/``updated_at``/``created_by_id``/``updated_by_id``.
    """

    __tablename__ = "onboarding_packets"

    id: Mapped[int] = mapped_column(primary_key=True)
    contact_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("contacts.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    company_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("companies.id", ondelete="SET NULL")
    )
    # Phase-3 proposal link; nullable in Phase 2.
    proposal_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("proposals.id", ondelete="SET NULL")
    )
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    token_expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    # Minted at completion; nullable-unique is fine on Postgres.
    download_token_hash: Mapped[str | None] = mapped_column(
        String(64), unique=True
    )
    download_token_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="active",
        server_default="active",
        index=True,
    )
    # Claim timestamp for the 3-phase /complete (stuck-completing reclaim).
    completing_since: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    # Server-side only — never echoed to the public page (verify compares it).
    recipient_email: Mapped[str] = mapped_column(String(255), nullable=False)
    recipient_name: Mapped[str | None] = mapped_column(String(255))
    # Drawn-once signature; ≤200 KB PNG; scrubbed on every terminal state.
    signer_signature_image: Mapped[bytes | None] = mapped_column(LargeBinary)
    signature_version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    signer_ip: Mapped[str | None] = mapped_column(String(45))
    signer_user_agent: Mapped[str | None] = mapped_column(Text)
    signer_timezone: Mapped[str | None] = mapped_column(String(100))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    queued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    first_opened_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_by_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL")
    )
    abandoned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class OnboardingPacketDocument(Base, AuditableMixin):
    """One template's frozen copy inside a packet (PDF + field snapshot).

    ``field_definitions`` is the frozen overlay copied from the template at
    create time; ``field_values`` is the recipient-supplied ``{id: value}``
    map (reassigned whole on each PATCH — no in-place mutation tracking).
    ``attachment_id`` is the completion fence: once set, the filled+stamped
    PDF lives as a contact ``Attachment`` and the doc is done.
    """

    __tablename__ = "onboarding_packet_documents"

    id: Mapped[int] = mapped_column(primary_key=True)
    packet_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("onboarding_packets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    display_order: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    source_template_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("onboarding_templates.id", ondelete="SET NULL")
    )
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    # v3 discriminator, frozen from the template at create time.
    kind: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="esign_pdf",
        server_default="esign_pdf",
    )
    # Per-packet physical PDF copy ref (storage.write convention). NULLABLE
    # since v3: questionnaire/upload docs carry no template-PDF copy — the
    # keystone relaxation behind P0-3/P0-5.
    pdf_path: Mapped[str | None] = mapped_column(Text)
    field_definitions: Mapped[list[dict]] = mapped_column(
        _FieldDefinitions, nullable=False, default=list, server_default="[]"
    )
    # {field_id: value}; mutable until the packet is claimed for completion.
    field_values: Mapped[dict] = mapped_column(
        _FieldDefinitions, nullable=False, default=dict, server_default="{}"
    )
    field_values_version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    requires_esign: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=sa.false()
    )
    esign_disclosure_snapshot: Mapped[str | None] = mapped_column(Text)
    esign_disclosure_version: Mapped[str | None] = mapped_column(String(50))
    consented_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Phase-B atomic lease (only one worker stamps a given doc at a time).
    stamp_lease_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    attachment_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("attachments.id", ondelete="SET NULL")
    )
    filled_pdf_error: Mapped[str | None] = mapped_column(Text)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        Index(
            "ix_onboarding_packet_documents_packet_order",
            "packet_id",
            "display_order",
            "id",
        ),
        CheckConstraint(
            "kind IN ('esign_pdf', 'questionnaire', 'upload_request')",
            name="ck_onboarding_packet_documents_kind",
        ),
    )


class OnboardingPacketUpload(Base):
    """One client-uploaded file on a ``file_upload`` question (v3, P0-6 fence).

    Written at FILL time (not completion): each file lands as its own
    ``contacts`` Attachment immediately, so the parent document's 1:1
    ``attachment_id`` fence stays reserved for the single summary/manifest
    artifact and a Phase-B retry never duplicates uploaded files. The answer
    JSONB (``field_values[field_id]``) references these rows by id; this table
    OWNS deletion (scrub deletes the Attachment via
    ``AttachmentService.delete_attachment`` then the row).

    Plain ``Base`` (not ``AuditableMixin``) — it carries its own ``created_at``
    and is never user-edited, mirroring the view-ledger row. ``token_hash``
    isolates which access link uploaded the file (forwarded-link safety);
    ``sensitive`` (gov-ID etc.) drives owner/admin read-auth and leaves the
    seam for a future ``completed_at + Nd`` retention sweep.
    """

    __tablename__ = "onboarding_packet_uploads"

    id: Mapped[int] = mapped_column(primary_key=True)
    packet_document_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("onboarding_packet_documents.id", ondelete="CASCADE"),
        nullable=False,
    )
    field_id: Mapped[str] = mapped_column(String(64), nullable=False)
    attachment_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("attachments.id", ondelete="SET NULL")
    )
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    byte_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(100), nullable=False)
    sensitive: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=sa.false()
    )
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # The index is declared ONCE here (matches migration 052) — do NOT also
    # set index=True on packet_document_id, or create_all would build a
    # second, migration-less index and drift from prod.
    __table_args__ = (
        Index(
            "ix_onboarding_packet_uploads_document", "packet_document_id"
        ),
    )


class OnboardingSecretValue(Base):
    """Encrypted ciphertext for one ``sensitive: true`` text answer (v3, F4).

    The §F decision-1 reversal: F4 passwords COLLECT + ENCRYPT AT REST, so this
    table SHIPS in v1 and carries rows (migration 053). A sensitive text field's
    plaintext NEVER enters ``field_values`` JSONB nor any generated PDF — only
    the Fernet ``ciphertext`` (keyed by ``ONBOARDING_FIELD_KEY``, see
    ``crypto.py``) lands here. The composite ``(packet_document_id, field_id)``
    PK is the upsert target ``patch_document`` writes in the SAME txn as the
    version bump; ``scrub_packet`` deletes these rows on every terminal
    transition (kind-agnostic) and the FK CASCADE drops them on a doc teardown.

    Plain ``Base`` (not ``AuditableMixin``) — it carries its own ``created_at``
    and is never user-edited, mirroring the upload/view-ledger rows.
    """

    __tablename__ = "onboarding_secret_values"

    packet_document_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("onboarding_packet_documents.id", ondelete="CASCADE"),
        nullable=False,
    )
    field_id: Mapped[str] = mapped_column(String(64), nullable=False)
    ciphertext: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    key_version: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, default=1, server_default="1"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        PrimaryKeyConstraint(
            "packet_document_id",
            "field_id",
            name="pk_onboarding_secret_values",
        ),
    )


class ProposalOnboardingSelection(Base, AuditableMixin):
    """Staff-curated onboarding template attached to a proposal (Phase 3, §4.7).

    One row per (proposal, template); ``display_order`` is the packet document
    order the auto-send trigger uses when the proposal is accepted. Both FKs
    CASCADE on delete — a soft-retire (``is_active=false``) keeps the row and
    the trigger skips it at fire time; only a hard template/proposal delete
    drops it. ``AuditableMixin`` supplies created/updated audit columns.

    The two unique constraints make the ordering gap-free and collision-free;
    the reorder service bumps rows to a temporary high offset before writing
    the final ``0..N-1`` values so a per-row UPDATE can't trip
    ``uq_proposal_onboarding_selection_order`` mid-reorder.
    """

    __tablename__ = "proposal_onboarding_selections"

    id: Mapped[int] = mapped_column(primary_key=True)
    # The proposal_id index is declared ONCE in __table_args__ below
    # (``ix_proposal_onboarding_selections_proposal``) to match migration 051
    # exactly — do NOT add ``index=True`` here too, or create_all (test/dev DBs)
    # would build a second, migration-less index and drift from prod.
    proposal_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("proposals.id", ondelete="CASCADE"),
        nullable=False,
    )
    template_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("onboarding_templates.id", ondelete="CASCADE"),
        nullable=False,
    )
    display_order: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )

    __table_args__ = (
        UniqueConstraint(
            "proposal_id", "template_id", name="uq_proposal_onboarding_selection"
        ),
        UniqueConstraint(
            "proposal_id",
            "display_order",
            name="uq_proposal_onboarding_selection_order",
        ),
        Index(
            "ix_proposal_onboarding_selections_proposal", "proposal_id"
        ),
    )


class OnboardingTemplateBundle(Base, AuditableMixin):
    """A named, ordered "saved packet" — a reusable list of template references
    staff assemble once (the wizard's output) and send to many clients.

    ``name`` is UNIQUE (matches the template name's case-sensitivity choice, D3).
    ``AuditableMixin`` supplies the created/updated audit columns. The ordered
    members live in ``OnboardingTemplateBundleItem``; deleting a bundle CASCADEs
    its items (the only cascade in this pair — see the item model).
    """

    __tablename__ = "onboarding_template_bundles"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=sa.true(), nullable=False
    )

    __table_args__ = (
        UniqueConstraint("name", name="uq_onboarding_template_bundles_name"),
    )


class OnboardingTemplateBundleItem(Base, AuditableMixin):
    """One template reference inside a bundle, at a given ``display_order``.

    ``bundle_id`` FK CASCADEs: deleting a bundle removes its items (this delete
    *does* happen). ``template_id`` FK has NO cascade — templates are only
    soft-retired (``service.retire`` sets ``is_active=false``), so a
    ``template_id`` cascade would be decorative and misleading (audit B4). A
    retired member is handled in-app: BLOCKED (never silently skipped) at send,
    and surfaced as "needs attention" in the bundle detail.

    The two unique constraints make the ordering gap-free and collision-free;
    the shared ``ordering.reorder_by_display_order`` bumps rows to a temporary
    high offset before writing the final ``0..N-1`` so a per-row UPDATE can't
    trip ``uq_onboarding_template_bundle_items_order`` mid-reorder.
    """

    __tablename__ = "onboarding_template_bundle_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    # The bundle_id index is declared ONCE in __table_args__ below
    # (``ix_onboarding_template_bundle_items_bundle``) to match the migration
    # exactly — do NOT add ``index=True`` here too, or create_all (test/dev DBs)
    # would build a second, migration-less index and drift from prod.
    bundle_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("onboarding_template_bundles.id", ondelete="CASCADE"),
        nullable=False,
    )
    # No ondelete: templates are soft-retired, never hard-deleted, so a cascade
    # here would be dead code (audit B4). Retired members are handled in-app.
    template_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("onboarding_templates.id"),
        nullable=False,
    )
    display_order: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )

    __table_args__ = (
        UniqueConstraint(
            "bundle_id",
            "template_id",
            name="uq_onboarding_template_bundle_items_template",
        ),
        UniqueConstraint(
            "bundle_id",
            "display_order",
            name="uq_onboarding_template_bundle_items_order",
        ),
        Index(
            "ix_onboarding_template_bundle_items_bundle", "bundle_id"
        ),
    )


class OnboardingPacketDocumentView(Base):
    """Per-token view row for a packet document (read-before-sign ledger).

    Clone of ``proposals.models.ProposalSigningDocumentView``: keyed on the
    SHA-256 of the access token so a forwarded link can't piggyback on
    another link's "viewed" rows. SAVEPOINT-idempotent insert in view_ledger.
    """

    __tablename__ = "onboarding_packet_document_views"

    id: Mapped[int] = mapped_column(primary_key=True)
    packet_document_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("onboarding_packet_documents.id", ondelete="CASCADE"),
        nullable=False,
    )
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    viewed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    ip_address: Mapped[str | None] = mapped_column(String(45))
    user_agent: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        UniqueConstraint(
            "packet_document_id",
            "token_hash",
            name="uq_onboarding_packet_doc_views_doc_token",
        ),
        Index(
            "ix_onboarding_packet_doc_views_token_hash", "token_hash"
        ),
        Index(
            "ix_onboarding_packet_doc_views_document", "packet_document_id"
        ),
    )
