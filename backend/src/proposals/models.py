"""Proposal models for AI-assisted sales proposals."""

from datetime import date, datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Date, DateTime, ForeignKey, Integer, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.core.mixins.auditable import AuditableMixin
from src.database import Base

if TYPE_CHECKING:
    from src.auth.models import User
    from src.companies.models import Company
    from src.contacts.models import Contact
    from src.opportunities.models import Opportunity
    from src.quotes.models import Quote


class Proposal(Base, AuditableMixin):
    """Proposal model for AI-generated sales proposals."""
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
    # billing wired up. `paid` is terminal.
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

    # Structured pricing. When set, the CRM uses these fields to spawn a
    # Stripe Invoice or Subscription on acceptance. `pricing_section`
    # (free-text, below) remains for human-readable detail but is not
    # used for billing math.
    #   payment_type: 'one_time' | 'subscription'
    #   recurring_interval: 'month' | 'year' (only when subscription)
    #   recurring_interval_count: 1 = monthly/yearly, 3 = quarterly,
    #                             6 = bi-yearly, etc.
    #   amount: total in currency major units (e.g. 500.00 USD)
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
    signed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    rejection_reason: Mapped[str | None] = mapped_column(Text)
    # Optional override for who may sign. NULL falls back to contact.email.
    designated_signer_email: Mapped[str | None] = mapped_column(String(255))

    # Stripe billing artifacts spawned on acceptance. Only one of
    # stripe_invoice_id / stripe_checkout_session_id will be set, based on
    # the linked Quote.payment_type: one_time -> invoice, subscription ->
    # checkout session. stripe_subscription_id is filled in by the
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
    quote: Mapped[Optional["Quote"]] = relationship(
        "Quote",
        lazy="joined",
    )
    views: Mapped[list["ProposalView"]] = relationship(
        "ProposalView",
        back_populates="proposal",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    # User links: rendered in the admin UI as "Created by" / "Owner".
    # Both FKs are SET NULL on user delete, so the relationships are optional.
    # `created_by_id` comes from AuditableMixin, so we identify it by string
    # to avoid referencing the declared_attr before it's resolved on the
    # mapped class.
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
