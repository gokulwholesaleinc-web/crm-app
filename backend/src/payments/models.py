"""Payment models for Stripe payment infrastructure."""

from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.core.mixins.auditable import AuditableMixin, TimestampMixin
from src.database import Base

if TYPE_CHECKING:
    from src.companies.models import Company
    from src.contacts.models import Contact
    from src.opportunities.models import Opportunity
    from src.quotes.models import Quote


class StripeCustomer(Base, TimestampMixin):
    """Maps CRM contacts/companies to Stripe customers."""
    __tablename__ = "stripe_customers"

    id: Mapped[int] = mapped_column(primary_key=True)

    # Link to CRM entities (one or both can be set)
    contact_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("contacts.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )
    company_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("companies.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )

    # Stripe identifiers
    stripe_customer_id: Mapped[str] = mapped_column(
        String(255), unique=True, index=True, nullable=False
    )
    email: Mapped[str | None] = mapped_column(String(255))
    name: Mapped[str | None] = mapped_column(String(255))

    # ORM relationships
    contact: Mapped[Optional["Contact"]] = relationship("Contact", lazy="joined")
    company: Mapped[Optional["Company"]] = relationship("Company", lazy="joined")


class Product(Base, AuditableMixin):
    """Product catalog synced with Stripe."""
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(String(1000))
    stripe_product_id: Mapped[str | None] = mapped_column(
        String(255), unique=True, index=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # Owner
    owner_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        index=True,
    )

    # ORM relationships
    prices: Mapped[list["Price"]] = relationship(
        "Price",
        back_populates="product",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class Price(Base, TimestampMixin):
    """Price entries for products, synced with Stripe."""
    __tablename__ = "prices"

    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("products.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    stripe_price_id: Mapped[str | None] = mapped_column(
        String(255), unique=True, index=True
    )
    amount: Mapped[float] = mapped_column(Numeric(precision=12, scale=2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="USD")
    recurring_interval: Mapped[str | None] = mapped_column(String(20))  # "month" or "year"
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # ORM relationships
    product: Mapped["Product"] = relationship("Product", back_populates="prices")


class Payment(Base, AuditableMixin):
    """Payment records tracking Stripe payment intents and checkout sessions."""
    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(primary_key=True)

    # Stripe identifiers
    stripe_payment_intent_id: Mapped[str | None] = mapped_column(
        String(255), unique=True, index=True
    )
    stripe_checkout_session_id: Mapped[str | None] = mapped_column(
        String(255), unique=True, index=True
    )
    stripe_invoice_id: Mapped[str | None] = mapped_column(
        String(255), unique=True, index=True, nullable=True
    )

    # Relations
    customer_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("stripe_customers.id", ondelete="SET NULL"),
        index=True,
    )
    opportunity_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("opportunities.id", ondelete="SET NULL"),
        index=True,
    )
    quote_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("quotes.id", ondelete="SET NULL"),
        index=True,
    )

    # Payment details
    amount: Mapped[float] = mapped_column(Numeric(precision=12, scale=2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="USD")
    status: Mapped[str] = mapped_column(
        String(20), default="pending", nullable=False
    )  # pending, sent, succeeded, failed, refunded
    payment_method: Mapped[str | None] = mapped_column(String(50))
    receipt_url: Mapped[str | None] = mapped_column(String(500))
    # Stripe-hosted URL the customer pays at — `hosted_invoice_url` for
    # invoices, Checkout Session URL for subscriptions. Persisted so the
    # CRM can re-share the link if the customer says they didn't get the
    # Stripe email (test mode, spam folder, wrong email on file).
    stripe_payment_url: Mapped[str | None] = mapped_column(Text)

    # Owner
    owner_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        index=True,
    )

    # ORM relationships
    customer: Mapped[Optional["StripeCustomer"]] = relationship(
        "StripeCustomer", lazy="joined"
    )
    opportunity: Mapped[Optional["Opportunity"]] = relationship(
        "Opportunity", lazy="joined"
    )
    quote: Mapped[Optional["Quote"]] = relationship(
        "Quote", lazy="joined"
    )


class Subscription(Base, AuditableMixin):
    """Subscription records tracking Stripe subscriptions."""
    __tablename__ = "subscriptions"

    id: Mapped[int] = mapped_column(primary_key=True)

    # Stripe identifier
    stripe_subscription_id: Mapped[str] = mapped_column(
        String(255), unique=True, index=True, nullable=False
    )

    # Relations
    customer_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("stripe_customers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Nullable: subscriptions created via Stripe Checkout / webhook flow
    # don't necessarily map to a local Price row at creation time.
    price_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("prices.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )

    # Subscription details
    status: Mapped[str] = mapped_column(
        String(20), default="active", nullable=False
    )  # active, past_due, canceled, trialing
    current_period_start: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    current_period_end: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    cancel_at_period_end: Mapped[bool] = mapped_column(Boolean, default=False)

    # Owner
    owner_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        index=True,
    )

    # ORM relationships
    customer: Mapped["StripeCustomer"] = relationship("StripeCustomer", lazy="joined")
    price: Mapped["Price"] = relationship("Price", lazy="joined")
