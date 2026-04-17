"""Company model for CRM accounts."""

from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.core.mixins.auditable import AuditableMixin
from src.database import Base

if TYPE_CHECKING:
    from src.contacts.models import Contact


class Company(Base, AuditableMixin):
    """Company model - organizations/accounts in the CRM system."""
    __tablename__ = "companies"

    id: Mapped[int] = mapped_column(primary_key=True)

    # Basic info
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    website: Mapped[str | None] = mapped_column(String(500))
    industry: Mapped[str | None] = mapped_column(String(100), index=True)
    company_size: Mapped[str | None] = mapped_column(String(50))  # 1-10, 11-50, etc.

    # Contact info
    phone: Mapped[str | None] = mapped_column(String(50))
    email: Mapped[str | None] = mapped_column(String(255))

    # Address
    address_line1: Mapped[str | None] = mapped_column(String(255))
    address_line2: Mapped[str | None] = mapped_column(String(255))
    city: Mapped[str | None] = mapped_column(String(100))
    state: Mapped[str | None] = mapped_column(String(100))
    postal_code: Mapped[str | None] = mapped_column(String(20))
    country: Mapped[str | None] = mapped_column(String(100))

    # Business info
    annual_revenue: Mapped[int | None] = mapped_column(BigInteger)
    employee_count: Mapped[int | None] = mapped_column(Integer)

    # Social
    linkedin_url: Mapped[str | None] = mapped_column(String(500))
    twitter_handle: Mapped[str | None] = mapped_column(String(100))

    # Additional
    description: Mapped[str | None] = mapped_column(Text)
    logo_url: Mapped[str | None] = mapped_column(String(500))

    # Segment
    segment: Mapped[str | None] = mapped_column(String(100), index=True, nullable=True)

    # Custom / transferable fields
    link_creative_tier: Mapped[str | None] = mapped_column(String(10))
    sow_url: Mapped[str | None] = mapped_column(String(500))
    account_manager: Mapped[str | None] = mapped_column(String(255))

    # Status
    status: Mapped[str] = mapped_column(String(20), default="prospect", index=True)  # prospect, customer, churned, merged

    # Forwarding pointer set by the dedup merge flow. When two companies are
    # merged the secondary is soft-deleted (status="merged") and this column
    # points at the surviving primary so lookups can follow the redirect.
    merged_into_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("companies.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Owner
    owner_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        index=True,
    )

    # Relationships
    contacts: Mapped[list["Contact"]] = relationship(
        "Contact",
        back_populates="company",
        lazy="dynamic",
    )

    __table_args__ = (
        Index("ix_companies_owner_created", "owner_id", "created_at"),
        UniqueConstraint("name", "owner_id", name="ix_companies_unique_name_owner"),
    )
