"""Gmail integration models."""

from datetime import datetime

from sqlalchemy import (
    JSON,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import TypeDecorator

from src.database import Base


class _AliasArray(TypeDecorator):
    """TEXT[] on Postgres, JSON-array on SQLite (the test path)."""

    impl = JSON
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(ARRAY(Text))
        return dialect.type_descriptor(JSON())

BackfillStatus = str  # "pending" | "running" | "complete" | "failed"


class GmailConnection(Base):
    """Per-user Gmail OAuth credentials for send + history polling."""

    __tablename__ = "gmail_connections"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    # Send-as addresses pulled from users.settings.sendAs.list. The
    # primary is reproduced lazily by `self_addresses`, so empty here
    # still classifies the primary correctly.
    aliases: Mapped[list[str]] = mapped_column(
        _AliasArray(), nullable=False, default=list, server_default="{}"
    )
    access_token: Mapped[str] = mapped_column(Text, nullable=False)
    refresh_token: Mapped[str | None] = mapped_column(Text, nullable=True)
    token_expiry: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    scopes: Mapped[str] = mapped_column(Text, nullable=False)
    history_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    watch_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
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

    __table_args__ = (
        Index("ix_gmail_connections_user_id", "user_id"),
        Index("ix_gmail_connections_email", "email"),
    )

    @property
    def is_active(self) -> bool:
        return self.revoked_at is None

    @property
    def scope_list(self) -> list[str]:
        return [s for s in (self.scopes or "").split() if s]

    @property
    def self_addresses(self) -> set[str]:
        """Lowercased primary + aliases. Drives sync's outbound-vs-inbound
        check and the matcher's self-exclude."""
        addrs: set[str] = set()
        for a in [self.email, *(self.aliases or [])]:
            clean = (a or "").strip().lower()
            if clean:
                addrs.add(clean)
        return addrs


class GmailBackfillState(Base):
    """Tracks progress of a Gmail historical backfill job per user."""

    __tablename__ = "gmail_backfill_state"

    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    processed_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)


class GmailSyncState(Base):
    """Per-user cursor for the Gmail history poller."""

    __tablename__ = "gmail_sync_state"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    last_history_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    last_synced_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    failure_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
