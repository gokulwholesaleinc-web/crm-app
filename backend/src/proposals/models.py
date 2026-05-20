"""Proposal models for CRM sales proposals."""

from datetime import date, datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import (
    JSON,
    BigInteger,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import TypeDecorator


class _SignatureCoords(TypeDecorator):
    """JSONB on Postgres, JSON on SQLite (test DB).

    Stores ``{page, x, y, width, height}`` for stamping the signature
    image onto ``master_contract_pdf_path``. NULL = auto-detect.
    """

    impl = JSON
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(JSONB())
        return dialect.type_descriptor(JSON())

from src.core.mixins.auditable import AuditableMixin
from src.database import Base

# Side-effect import: the quotes router was unmounted 2026-05-14 so no
# other startup path pulls ``src.quotes.models`` into ``Base.metadata``.
# Proposal.quote_id below still declares ``ForeignKey("quotes.id", …)``
# for legacy provenance, and SQLAlchemy resolves that FK lazily when
# building DELETE statements — without the Quote mapper registered, the
# resolution raises NoReferencedTableError and DELETE /api/proposals/{id}
# 500s. Importing here keeps the FK enforceable without re-mounting the
# router or shipping a destructive alembic migration. ``noqa: F401``
# because the import is purely for the registration side-effect; the
# ``assert`` below makes the dependency load-bearing so an auto-cleaner
# (ruff --fix F401, pyupgrade, etc.) that strips the comment-only import
# trips an immediate ImportError at module load instead of waiting for
# the next prod DELETE to discover the regression.
from src.quotes import models as _quotes_models  # noqa: F401

assert "quotes" in Base.metadata.tables, (
    "src.quotes.models import was stripped; restore the side-effect "
    "import above so Proposal.quote_id FK can resolve."
)

if TYPE_CHECKING:
    from src.auth.models import User
    from src.companies.models import Company
    from src.contacts.models import Contact
    from src.opportunities.models import Opportunity


class ProposalSigningDocument(Base, AuditableMixin):
    """PDF attached to a proposal that must receive the signer signature."""
    __tablename__ = "proposal_signing_documents"

    id: Mapped[int] = mapped_column(primary_key=True)
    proposal_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("proposals.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    file_size: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    content_type: Mapped[str] = mapped_column(
        String(100),
        default="application/pdf",
        nullable=False,
    )
    pdf_path: Mapped[str] = mapped_column(Text, nullable=False)
    signature_field_coords: Mapped[dict | None] = mapped_column(_SignatureCoords)
    date_field_coords: Mapped[dict | None] = mapped_column(_SignatureCoords)
    signed_pdf_path: Mapped[str | None] = mapped_column(Text)
    signed_pdf_error: Mapped[str | None] = mapped_column(Text)
    display_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    proposal: Mapped["Proposal"] = relationship(
        "Proposal",
        back_populates="signing_documents",
    )

    __table_args__ = (
        Index(
            "ix_proposal_signing_documents_proposal_order",
            "proposal_id",
            "display_order",
            "id",
        ),
    )


class ProposalSigningDocumentView(Base):
    """Per-public-token view row for signable PDFs."""

    __tablename__ = "proposal_signing_document_views"

    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("proposal_signing_documents.id", ondelete="CASCADE"),
        nullable=False,
    )
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    viewed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    ip_address: Mapped[str | None] = mapped_column(String(45))
    user_agent: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        UniqueConstraint(
            "document_id",
            "token_hash",
            name="uq_proposal_signing_document_views_doc_token",
        ),
        Index("ix_proposal_signing_document_views_token_hash", "token_hash"),
        Index("ix_proposal_signing_document_views_document", "document_id"),
    )


class Proposal(Base, AuditableMixin):
    """Proposal model for CRM sales documents."""
    __tablename__ = "proposals"

    id: Mapped[int] = mapped_column(primary_key=True)

    # Identification
    proposal_number: Mapped[str] = mapped_column(
        String(50), unique=True, index=True, nullable=False
    )
    # Unguessable public-link token — see Quote.public_token for rationale.
    public_token: Mapped[str | None] = mapped_column(
        String(64), unique=True, index=True, nullable=True
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    content: Mapped[str | None] = mapped_column(Text)

    # Relationships to other entities
    opportunity_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("opportunities.id", ondelete="SET NULL"),
        index=True,
    )
    contact_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("contacts.id", ondelete="SET NULL"),
        index=True,
    )
    company_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("companies.id", ondelete="SET NULL"),
        index=True,
    )
    # Legacy FK column — quotes router unmounted 2026-05-14. Column kept
    # nullable so historical Proposal rows duplicated from quotes still
    # have queryable provenance. No new writes; ORM relationship dropped.
    quote_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("quotes.id", ondelete="SET NULL"),
        index=True,
    )

    # Status lifecycle:
    #   draft -> sent -> viewed -> accepted -> (awaiting_payment) -> paid
    #                                      \-> rejected
    # `awaiting_payment` is the brief window between e-sign and Stripe
    # webhook confirming payment; it lets the UI show "Invoice sent,
    # waiting on payment" instead of just "Accepted" for deals that have
    # payment wired up. `paid` is terminal.
    status: Mapped[str] = mapped_column(String(20), default="draft", nullable=False)

    # Content sections
    cover_letter: Mapped[str | None] = mapped_column(Text)
    executive_summary: Mapped[str | None] = mapped_column(Text)
    scope_of_work: Mapped[str | None] = mapped_column(Text)
    pricing_section: Mapped[str | None] = mapped_column(Text)
    timeline: Mapped[str | None] = mapped_column(Text)
    terms: Mapped[str | None] = mapped_column(Text)

    # Validity
    valid_until: Mapped[date | None] = mapped_column(Date)

    # Legacy structured payment fields. Payments are now created from the
    # Payments module; these remain for old records and explicit retry paths.
    # `pricing_section` (free-text, below) remains for human-readable detail.
    #   payment_type: 'one_time' | 'subscription'
    #   recurring_interval: 'month' | 'year' (only when subscription)
    #   recurring_interval_count: 1 = monthly/yearly, 3 = quarterly,
    #                             6 = bi-yearly, etc.
    #   amount: total in currency major units
    payment_type: Mapped[str] = mapped_column(
        String(20), default="one_time", nullable=False
    )
    recurring_interval: Mapped[str | None] = mapped_column(String(20))
    recurring_interval_count: Mapped[int | None] = mapped_column(Integer)
    amount: Mapped[float | None] = mapped_column(Numeric(12, 2))
    currency: Mapped[str] = mapped_column(String(3), default="USD", nullable=False)

    # Status timestamps
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    viewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    rejected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # View tracking
    view_count: Mapped[int] = mapped_column(Integer, default=0)
    last_viewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # E-signature fields (captured when client accepts via public link)
    signer_name: Mapped[str | None] = mapped_column(String(255))
    signer_email: Mapped[str | None] = mapped_column(String(255))
    signer_ip: Mapped[str | None] = mapped_column(String(45))
    signer_user_agent: Mapped[str | None] = mapped_column(Text)
    signer_timezone: Mapped[str | None] = mapped_column(String(100))
    signed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    rejection_reason: Mapped[str | None] = mapped_column(Text)
    # Optional override for who may sign. NULL falls back to contact.email.
    designated_signer_email: Mapped[str | None] = mapped_column(String(255))

    # Sign-to-Confirm artifacts. The drawn signature lives inline as raw
    # PNG bytes (~5–30 KB typical) so audit-trail rendering doesn't need
    # an extra R2 round-trip and a signed copy can be rebuilt from the
    # row alone if R2 loses the stamped PDF.
    signature_image: Mapped[bytes | None] = mapped_column(LargeBinary)
    # R2 key of the optional master service agreement PDF uploaded by
    # the rep. When set, the accept endpoint stamps the signature image
    # onto a copy of this PDF + an audit page and persists the result
    # at ``signed_pdf_path``. NULL = signature image + audit log alone,
    # which is ESIGN-Act-compliant on its own.
    master_contract_pdf_path: Mapped[str | None] = mapped_column(Text)
    # Where in the master PDF to stamp: ``{page:int, x:float, y:float,
    # width:float, height:float}`` in PDF points (origin = bottom-left).
    # NULL = auto-detect (last page, bottom-right).
    signature_field_coords: Mapped[dict | None] = mapped_column(_SignatureCoords)
    # Where in the master PDF to stamp the signer's local date in MM-DD-YYYY.
    date_field_coords: Mapped[dict | None] = mapped_column(_SignatureCoords)
    # R2 key of the stamped + audit-appended signed PDF.
    signed_pdf_path: Mapped[str | None] = mapped_column(Text)
    # Most-recent stamp/upload failure from ``_maybe_stamp_master_pdf``.
    # Set when the fail-soft path swallows a PdfReadError / R2 ClientError /
    # other exception so the CRM UI can render a re-stamp banner instead
    # of leaving the operator wondering why no signed PDF ever materialized.
    # Cleared on the next successful stamp.
    signed_pdf_error: Mapped[str | None] = mapped_column(Text)
    # Per-proposal override of the T&C body rendered inside the signing
    # modal. NULL falls back to ``tenant_settings.default_terms_and_conditions``.
    terms_and_conditions: Mapped[str | None] = mapped_column(Text)

    # Stripe billing artifacts. Populated only via the explicit Retry
    # Billing endpoint (accept-time auto-spawn was removed 2026-05-14
    # per Lorenzo's manual-billing model). Only one of stripe_invoice_id /
    # stripe_checkout_session_id will be set, based on the linked
    # Quote.payment_type: one_time -> invoice, subscription -> checkout
    # session. stripe_subscription_id is filled in by the
    # checkout.session.completed webhook when the client completes setup.
    stripe_invoice_id: Mapped[str | None] = mapped_column(String(255), index=True)
    stripe_subscription_id: Mapped[str | None] = mapped_column(
        String(255), index=True
    )
    stripe_checkout_session_id: Mapped[str | None] = mapped_column(
        String(255), index=True
    )
    stripe_payment_url: Mapped[str | None] = mapped_column(Text)
    invoice_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Most-recent Stripe-spawn failure (bad key, customer resolution,
    # Stripe API error). Populated by `_maybe_spawn_billing` when the
    # try/except swallows a ValueError so the CRM UI can show the admin
    # "billing setup failed — retry" instead of a silent "accepted" with
    # no payment link. Cleared on successful retry.
    billing_error: Mapped[str | None] = mapped_column(Text)

    # Owner
    owner_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        index=True,
    )

    # ORM relationships
    opportunity: Mapped[Optional["Opportunity"]] = relationship(
        "Opportunity",
        lazy="joined",
    )
    contact: Mapped[Optional["Contact"]] = relationship(
        "Contact",
        lazy="joined",
    )
    company: Mapped[Optional["Company"]] = relationship(
        "Company",
        lazy="joined",
    )
    # ``quote`` ORM relationship removed 2026-05-14 — see ``quote_id`` above.
    views: Mapped[list["ProposalView"]] = relationship(
        "ProposalView",
        back_populates="proposal",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    # `created_by_id` comes from AuditableMixin — string FK ref handles
    # the declared_attr resolution order.
    created_by_user: Mapped[Optional["User"]] = relationship(
        "User",
        foreign_keys="Proposal.created_by_id",
        lazy="joined",
    )
    owner: Mapped[Optional["User"]] = relationship(
        "User",
        foreign_keys=[owner_id],
        lazy="joined",
    )
    signing_documents: Mapped[list[ProposalSigningDocument]] = relationship(
        "ProposalSigningDocument",
        back_populates="proposal",
        cascade="all, delete-orphan",
        order_by=(ProposalSigningDocument.display_order, ProposalSigningDocument.id),
        lazy="selectin",
    )


class ProposalTemplate(Base, AuditableMixin):
    """Reusable proposal templates with merge variable placeholders."""
    __tablename__ = "proposal_templates"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    body: Mapped[str] = mapped_column(Text, nullable=False, default="")
    legal_terms: Mapped[str | None] = mapped_column(Text, nullable=True)
    category: Mapped[str | None] = mapped_column(String(100), nullable=True)
    is_default: Mapped[bool] = mapped_column(default=False)
    owner_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )


class ProposalView(Base):
    """Tracks individual views of a proposal."""
    __tablename__ = "proposal_views"

    id: Mapped[int] = mapped_column(primary_key=True)
    proposal_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("proposals.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    viewed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    ip_address: Mapped[str | None] = mapped_column(String(45))
    user_agent: Mapped[str | None] = mapped_column(Text)

    # ORM relationship
    proposal: Mapped["Proposal"] = relationship("Proposal", back_populates="views")
