"""Company model for CRM accounts."""

from typing import Optional, List, TYPE_CHECKING
from sqlalchemy import String, Integer, ForeignKey, Text, BigInteger
from sqlalchemy.orm import Mapped, mapped_column, relationship
from src.database import Base
from src.core.mixins.auditable import AuditableMixin

if TYPE_CHECKING:
    from src.contacts.models import Contact


class Company(Base, AuditableMixin):
    """Company model - organizations/accounts in the CRM system."""
    __tablename__ = "companies"

    id: Mapped[int] = mapped_column(primary_key=True)

    # Basic info
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    website: Mapped[Optional[str]] = mapped_column(String(500))
    industry: Mapped[Optional[str]] = mapped_column(String(100))
    company_size: Mapped[Optional[str]] = mapped_column(String(50))  # 1-10, 11-50, etc.

    # Contact info
    phone: Mapped[Optional[str]] = mapped_column(String(50))
    email: Mapped[Optional[str]] = mapped_column(String(255))

    # Address
    address_line1: Mapped[Optional[str]] = mapped_column(String(255))
    address_line2: Mapped[Optional[str]] = mapped_column(String(255))
    city: Mapped[Optional[str]] = mapped_column(String(100))
    state: Mapped[Optional[str]] = mapped_column(String(100))
    postal_code: Mapped[Optional[str]] = mapped_column(String(20))
    country: Mapped[Optional[str]] = mapped_column(String(100))

    # Business info
    annual_revenue: Mapped[Optional[int]] = mapped_column(BigInteger)
    employee_count: Mapped[Optional[int]] = mapped_column(Integer)

    # Social
    linkedin_url: Mapped[Optional[str]] = mapped_column(String(500))
    twitter_handle: Mapped[Optional[str]] = mapped_column(String(100))

    # Additional
    description: Mapped[Optional[str]] = mapped_column(Text)
    logo_url: Mapped[Optional[str]] = mapped_column(String(500))

    # Status
    status: Mapped[str] = mapped_column(String(20), default="prospect")  # prospect, customer, churned

    # Owner
    owner_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        index=True,
    )

    # Relationships
    contacts: Mapped[List["Contact"]] = relationship(
        "Contact",
        back_populates="company",
        lazy="dynamic",
    )
