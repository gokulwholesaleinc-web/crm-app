"""Email models for tracking sent and received emails."""

from datetime import date, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    event,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from src.database import Base


class EmailQueue(Base):
    """Email queue model - tracks all outbound emails with open/click tracking."""
    __tablename__ = "email_queue"

    id: Mapped[int] = mapped_column(primary_key=True)
    to_email: Mapped[str] = mapped_column(String(255), nullable=False)
    from_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    subject: Mapped[str] = mapped_column(String(500), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    cc: Mapped[str | None] = mapped_column(Text, nullable=True)
    bcc: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Status tracking
    status: Mapped[str] = mapped_column(
        String(20), default="pending", nullable=False
    )  # pending, sent, failed, retry
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    next_retry_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Open/Click tracking
    opened_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    clicked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    open_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    click_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Entity link (polymorphic)
    entity_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    entity_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Template / Campaign references
    template_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("email_templates.id", ondelete="SET NULL"), nullable=True
    )
    campaign_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("campaigns.id", ondelete="SET NULL"), nullable=True
    )

    # Who sent it
    sent_by_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    # Provider that delivered the email — historically also used "resend"
    # before the in-house Resend integration was retired. New rows are
    # always tagged "gmail" by the dispatcher; legacy rows keep their
    # original value for activity-history accuracy.
    sent_via: Mapped[str] = mapped_column(
        String(20), default="gmail", server_default="gmail", nullable=False
    )
    message_id: Mapped[str | None] = mapped_column(String(500), nullable=True)
    thread_id: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Lowercased + deduped bare addresses pulled from From/To/CC/BCC at write
    # time. Used to scope visibility per-user via overlap with the viewer's
    # gmail_connections.email set.
    participant_emails: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, server_default="{}", default=list
    )

    __table_args__ = (
        Index("ix_email_queue_entity", "entity_type", "entity_id"),
        Index("ix_email_queue_status", "status"),
        Index("ix_email_queue_sent_by", "sent_by_id"),
        Index("ix_email_queue_thread_id", "thread_id"),
        Index("ix_email_queue_participants", "participant_emails", postgresql_using="gin"),
    )


class EmailSettings(Base):
    """Email sending settings - daily limits and warmup configuration."""
    __tablename__ = "email_settings"

    id: Mapped[int] = mapped_column(primary_key=True)
    daily_send_limit: Mapped[int] = mapped_column(Integer, default=1000, nullable=False)
    warmup_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    warmup_start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    warmup_target_daily: Mapped[int] = mapped_column(Integer, default=1000, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class InboundEmail(Base):
    """Inbound email model - stores emails received via Resend webhook."""
    __tablename__ = "inbound_emails"

    id: Mapped[int] = mapped_column(primary_key=True)
    resend_email_id: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    from_email: Mapped[str] = mapped_column(String(255), nullable=False)
    to_email: Mapped[str] = mapped_column(String(255), nullable=False)
    cc: Mapped[str | None] = mapped_column(Text, nullable=True)
    bcc: Mapped[str | None] = mapped_column(Text, nullable=True)
    subject: Mapped[str] = mapped_column(String(500), nullable=False)
    body_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    body_html: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Threading
    message_id: Mapped[str | None] = mapped_column(String(500), nullable=True)
    in_reply_to: Mapped[str | None] = mapped_column(String(500), nullable=True)
    thread_id: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Attachments metadata
    attachments: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # Entity link (polymorphic - auto-matched to contact)
    entity_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    entity_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Timestamps
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Lowercased + deduped bare addresses pulled from From/To/CC/BCC at
    # ingest time. See EmailQueue.participant_emails.
    participant_emails: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, server_default="{}", default=list
    )

    __table_args__ = (
        Index("ix_inbound_emails_entity", "entity_type", "entity_id"),
        Index("ix_inbound_emails_from", "from_email"),
        Index("ix_inbound_emails_thread_id", "thread_id"),
        Index("ix_inbound_emails_participants", "participant_emails", postgresql_using="gin"),
    )


def _autofill_participants(_mapper, _conn, target) -> None:
    """Populate participant_emails from From/To/CC/BCC if caller didn't set it.

    Acts as a safety net: any InboundEmail/EmailQueue inserted without an
    explicit participant set (tests, ad-hoc admin scripts, future code paths
    we haven't audited) still gets a usable address index. Helpers that pass
    a precomputed list win because we only fill when the column is empty.
    """
    if target.participant_emails:
        return
    from src.email.participants import collect_participants

    from_email = getattr(target, "from_email", None)
    to_email = getattr(target, "to_email", None)
    cc = getattr(target, "cc", None)
    bcc = getattr(target, "bcc", None)
    target.participant_emails = collect_participants(from_email, to_email, cc, bcc)


event.listen(InboundEmail, "before_insert", _autofill_participants)
event.listen(EmailQueue, "before_insert", _autofill_participants)
