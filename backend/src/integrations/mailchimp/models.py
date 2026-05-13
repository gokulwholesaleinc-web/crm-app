"""Mailchimp integration models."""

from datetime import datetime

from sqlalchemy import (
    JSON,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import TypeDecorator

from src.database import Base


class _BlockedAudienceIds(TypeDecorator):
    """TEXT[] on Postgres, JSON-array on SQLite (the test path).

    Mirrors ``email/models.py::_ParticipantEmails`` so the unit-test suite,
    which boots against in-memory SQLite, can build the table at all.
    """

    impl = JSON
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(ARRAY(String(64)))
        return dialect.type_descriptor(JSON())


class MailchimpConnection(Base):
    """Tenant-level Mailchimp Marketing API credentials.

    Mailchimp keys carry a ``-<dc>`` suffix that identifies the data
    center (e.g. ``...-us19``). We split it into ``api_key`` and
    ``server_prefix`` at connect time so callers don't have to re-parse
    the key on every request.
    """

    __tablename__ = "mailchimp_connections"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
    )
    api_key: Mapped[str] = mapped_column(Text, nullable=False)
    server_prefix: Mapped[str] = mapped_column(String(16), nullable=False)

    default_audience_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    default_audience_name: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Audience ids that admins have marked off-limits for CRM sends. The
    # frontend audience picker filters these out; the send path does NOT
    # currently hard-reject (UI-only block). Defense-in-depth on top of
    # the per-send static-segment scoping shipped in PR #320.
    blocked_audience_ids: Mapped[list[str]] = mapped_column(
        _BlockedAudienceIds(), nullable=False, default=list, server_default="{}"
    )

    account_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    account_login_id: Mapped[str | None] = mapped_column(String(255), nullable=True)

    connected_by_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    connected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    @property
    def is_active(self) -> bool:
        return self.revoked_at is None

    @property
    def base_url(self) -> str:
        return f"https://{self.server_prefix}.api.mailchimp.com/3.0"
