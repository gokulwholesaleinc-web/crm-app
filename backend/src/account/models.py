"""ORM for account-settings tables (notification prefs + display prefs).

Both rows are 1:1 with `users` and lazy-created on first GET via
``AccountPrefsService.get_or_create_*``. The ``event_matrix`` JSONB
holds the event×channel toggle map; see ``notification_gate`` for the
opt-out semantics.
"""

from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import TypeDecorator

from src.database import Base


class _EventMatrix(TypeDecorator):
    """JSONB on Postgres, JSON on SQLite (test DB)."""

    impl = JSON
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(JSONB())
        return dialect.type_descriptor(JSON())


class UserNotificationPrefs(Base):
    __tablename__ = "user_notification_prefs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )

    in_app_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )
    email_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )
    email_digest: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default=text("'instant'")
    )

    quiet_hours_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    quiet_hours_start: Mapped[str | None] = mapped_column(String(5), nullable=True)
    quiet_hours_end: Mapped[str | None] = mapped_column(String(5), nullable=True)

    # server_default lives in migration 022 (Postgres-side `'{}'::jsonb`);
    # the Python-side default keeps fresh inserts working in tests where
    # the column type degrades to JSON on SQLite.
    event_matrix: Mapped[dict] = mapped_column(
        _EventMatrix, nullable=False, default=dict
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


class UserPreferences(Base):
    __tablename__ = "user_preferences"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )

    timezone: Mapped[str] = mapped_column(
        String(64), nullable=False, server_default=text("'America/Chicago'")
    )
    locale: Mapped[str] = mapped_column(
        String(10), nullable=False, server_default=text("'en-US'")
    )
    date_format: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default=text("'MM/DD/YYYY'")
    )
    time_format: Mapped[str] = mapped_column(
        String(5), nullable=False, server_default=text("'12h'")
    )
    week_start: Mapped[str] = mapped_column(
        String(10), nullable=False, server_default=text("'sunday'")
    )
    currency_display: Mapped[str] = mapped_column(
        String(8), nullable=False, server_default=text("'USD'")
    )
    theme: Mapped[str] = mapped_column(
        String(10), nullable=False, server_default=text("'system'")
    )
    default_landing: Mapped[str] = mapped_column(
        String(64), nullable=False, server_default=text("'/dashboard'")
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
