"""Persistent Stripe webhook idempotency log.

Keeps a small row per processed Stripe event so that replayed signed
payloads don't re-fire handlers (re-sending receipts, double-inserting
renewal Payment rows, etc). Lives in its own module to avoid bloating
`payments/models.py`.
"""

from datetime import datetime
from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from src.database import Base


class WebhookEvent(Base):
    """One row per Stripe event_id we've already processed."""
    __tablename__ = "webhook_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[str] = mapped_column(
        String(255), unique=True, index=True, nullable=False
    )
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
