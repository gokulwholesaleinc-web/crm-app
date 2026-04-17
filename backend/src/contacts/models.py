"""Contact model for CRM contacts."""

from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.core.mixins.auditable import AuditableMixin
from src.database import Base

if TYPE_CHECKING:
    from src.companies.models import Company


class Contact(Base, AuditableMixin):
    """Contact model - individuals in the CRM system."""
    __tablename__ = "contacts"

    id: Mapped[int] = mapped_column(primary_key=True)

    # Basic info
    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)
    email: Mapped[str | None] = mapped_column(String(255), index=True)
    phone: Mapped[str | None] = mapped_column(String(50))
    mobile: Mapped[str | None] = mapped_column(String(50))

    # Professional info
    job_title: Mapped[str | None] = mapped_column(String(100))
    department: Mapped[str | None] = mapped_column(String(100))

    # Company relationship
    company_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("companies.id", ondelete="SET NULL"),
        index=True,
    )

    # Address
    address_line1: Mapped[str | None] = mapped_column(String(255))
    address_line2: Mapped[str | None] = mapped_column(String(255))
    city: Mapped[str | None] = mapped_column(String(100))
    state: Mapped[str | None] = mapped_column(String(100))
    postal_code: Mapped[str | None] = mapped_column(String(20))
    country: Mapped[str | None] = mapped_column(String(100))

    # Social
    linkedin_url: Mapped[str | None] = mapped_column(String(500))
    twitter_handle: Mapped[str | None] = mapped_column(String(100))

    # Additional
    description: Mapped[str | None] = mapped_column(Text)
    avatar_url: Mapped[str | None] = mapped_column(String(500))

    # Status
    status: Mapped[str] = mapped_column(String(20), default="active", index=True)  # active, inactive, archived

    # Soft-delete timestamp. Contacts are never hard-deleted — per project
    # rule (feedback_delete_sales_only.md) deleting a contact would destroy
    # history tied to their AR ledger and activities. ``deleted_at`` is NULL
    # for live contacts; set to the archive time when the delete endpoint or
    # a dedup merge soft-deletes the row. Code paths that read active
    # contacts MUST filter by ``deleted_at IS NULL``.
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)

    # Forwarding pointer set by the dedup merge flow. When two contacts are
    # merged, the secondary is soft-deleted and ``merged_into_id`` points at
    # the surviving primary. Downstream code can follow the pointer to find
    # the canonical record without looking up the audit log.
    merged_into_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("contacts.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Owner (assigned user)
    owner_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        index=True,
    )

    # Sales code
    sales_code: Mapped[str | None] = mapped_column(String(100), index=True, nullable=True)

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
        Index("ix_contacts_owner_created", "owner_id", "created_at"),
        UniqueConstraint("email", name="ix_contacts_unique_email"),
    )
