"""Contact model for CRM contacts."""

from typing import Optional, TYPE_CHECKING
from sqlalchemy import String, Integer, ForeignKey, Text, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from src.database import Base
from src.core.mixins.auditable import AuditableMixin

if TYPE_CHECKING:
    from src.companies.models import Company


class Contact(Base, AuditableMixin):
    """Contact model - individuals in the CRM system."""
    __tablename__ = "contacts"

    id: Mapped[int] = mapped_column(primary_key=True)

    # Basic info
    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)
    email: Mapped[Optional[str]] = mapped_column(String(255), index=True)
    phone: Mapped[Optional[str]] = mapped_column(String(50))
    mobile: Mapped[Optional[str]] = mapped_column(String(50))

    # Professional info
    job_title: Mapped[Optional[str]] = mapped_column(String(100))
    department: Mapped[Optional[str]] = mapped_column(String(100))

    # Company relationship
    company_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("companies.id", ondelete="SET NULL"),
        index=True,
    )

    # Address
    address_line1: Mapped[Optional[str]] = mapped_column(String(255))
    address_line2: Mapped[Optional[str]] = mapped_column(String(255))
    city: Mapped[Optional[str]] = mapped_column(String(100))
    state: Mapped[Optional[str]] = mapped_column(String(100))
    postal_code: Mapped[Optional[str]] = mapped_column(String(20))
    country: Mapped[Optional[str]] = mapped_column(String(100))

    # Social
    linkedin_url: Mapped[Optional[str]] = mapped_column(String(500))
    twitter_handle: Mapped[Optional[str]] = mapped_column(String(100))

    # Additional
    description: Mapped[Optional[str]] = mapped_column(Text)
    avatar_url: Mapped[Optional[str]] = mapped_column(String(500))

    # Status
    status: Mapped[str] = mapped_column(String(20), default="active")  # active, inactive

    # Owner (assigned user)
    owner_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        index=True,
    )

    # Relationships
    company: Mapped[Optional["Company"]] = relationship(
        "Company",
        back_populates="contacts",
        lazy="joined",
    )

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}"

    __table_args__ = (
        Index("ix_contacts_name", "first_name", "last_name"),
    )
