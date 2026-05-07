"""Contract model for tracking contracts associated with contacts and companies."""

from datetime import date as date_type
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Date, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.core.mixins.auditable import AuditableMixin
from src.database import Base

if TYPE_CHECKING:
    from src.companies.models import Company
    from src.contacts.models import Contact


class Contract(Base, AuditableMixin):
    """Contract model - tracks contracts linked to contacts and companies."""
    __tablename__ = "contracts"

    id: Mapped[int] = mapped_column(primary_key=True)

    # Basic info
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    scope: Mapped[str | None] = mapped_column(Text)

    # Financials
    value: Mapped[float | None] = mapped_column(Float)
    currency: Mapped[str] = mapped_column(String(3), default="USD")

    # Dates
    start_date: Mapped[date_type | None] = mapped_column(Date)
    end_date: Mapped[date_type | None] = mapped_column(Date)

    # Status taxonomy:
    #   draft       — being authored
    #   sent        — emailed to the customer for signature; sign_token live
    #   signed      — countersigned by the customer; awaiting start_date
    #   active      — start_date has passed; the agreement is in force
    #   expired     — end_date has passed (manual or daily-cron transition)
    #   terminated  — manually ended early
    status: Mapped[str] = mapped_column(String(20), default="draft", index=True)

    # Relationships
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

    # Owner
    owner_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        index=True,
    )

    # E-sign workflow state
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sign_token: Mapped[str | None] = mapped_column(String(64))
    sign_token_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    signed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    signed_by_name: Mapped[str | None] = mapped_column(String(255))
    signed_signature_b64: Mapped[str | None] = mapped_column(Text)
    signed_ip: Mapped[str | None] = mapped_column(String(45))
    signed_ua: Mapped[str | None] = mapped_column(Text)
    signed_pdf_r2_key: Mapped[str | None] = mapped_column(String(255))

    # Expiring-soon notification dedup (set when the daily scan fires).
    expiring_notified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Relationships
    contact: Mapped[Optional["Contact"]] = relationship(
        "Contact",
        lazy="joined",
    )
    company: Mapped[Optional["Company"]] = relationship(
        "Company",
        lazy="joined",
    )
