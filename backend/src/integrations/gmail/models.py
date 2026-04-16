"""Gmail integration models.

Patterned after src/integrations/google_calendar/models.py. Each user has at most one
active GmailConnection; GmailSyncState tracks the last processed Gmail historyId so
the 90s poller can diff forward via users.history.list.
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from src.database import Base


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
    access_token: Mapped[str] = mapped_column(Text, nullable=False)
    refresh_token: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    token_expiry: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    scopes: Mapped[str] = mapped_column(Text, nullable=False)
    history_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    watch_expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    revoked_at: Mapped[Optional[datetime]] = mapped_column(
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


class GmailSyncState(Base):
    """Cursor state for the Gmail history poller.

    One row per user. last_history_id is the Gmail historyId we've already processed;
    next poll passes it to users.history.list(startHistoryId=...).
    """

    __tablename__ = "gmail_sync_state"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    last_history_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    last_synced_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
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
