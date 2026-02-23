"""Contract model for tracking contracts associated with contacts and companies."""

from datetime import date as date_type
from typing import Optional, TYPE_CHECKING
from sqlalchemy import String, Integer, Float, Text, Date, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from src.database import Base
from src.core.mixins.auditable import AuditableMixin

if TYPE_CHECKING:
    from src.contacts.models import Contact
    from src.companies.models import Company


class Contract(Base, AuditableMixin):
    """Contract model - tracks contracts linked to contacts and companies."""
    __tablename__ = "contracts"

    id: Mapped[int] = mapped_column(primary_key=True)

    # Basic info
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    scope: Mapped[Optional[str]] = mapped_column(Text)

    # Financials
    value: Mapped[Optional[float]] = mapped_column(Float)
    currency: Mapped[str] = mapped_column(String(3), default="USD")

    # Dates
    start_date: Mapped[Optional[date_type]] = mapped_column(Date)
    end_date: Mapped[Optional[date_type]] = mapped_column(Date)

    # Status: draft, active, expired, terminated
    status: Mapped[str] = mapped_column(String(20), default="draft", index=True)

    # Relationships
    contact_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("contacts.id", ondelete="SET NULL"),
        index=True,
    )
    company_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("companies.id", ondelete="SET NULL"),
        index=True,
    )

    # Owner
    owner_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        index=True,
    )

    # Relationships
    contact: Mapped[Optional["Contact"]] = relationship(
        "Contact",
        lazy="joined",
    )
    company: Mapped[Optional["Company"]] = relationship(
        "Company",
        lazy="joined",
    )
