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
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
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
    # Per-packet physical PDF copy ref (storage.write convention).
    pdf_path: Mapped[str] = mapped_column(Text, nullable=False)
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
