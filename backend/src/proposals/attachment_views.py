"""Per-token attachment-view ledger that gates the public accept flow.

A proposal can carry one or more PDF attachments (insurance certificates,
SOWs, NDAs). The signer must open every attachment from the public link
before they're allowed to accept. ``proposal_attachment_views`` records
which attachments have been opened *for this token* — using the SHA-256
hash of the public token rather than the raw token so the ledger is
useless if the row is leaked.
"""

from __future__ import annotations

import hashlib
from datetime import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    select,
)
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from src.attachments.models import Attachment
from src.database import Base


def _hash_token(token: str) -> str:
    """SHA-256 of the public token, lowercased hex.

    Used as the dedup key for the view ledger so a forwarded public link
    can't piggyback on another link's "viewed" rows.
    """
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class ProposalAttachmentView(Base):
    """Audit row written each time a public-link visitor downloads an attachment."""

    __tablename__ = "proposal_attachment_views"

    id: Mapped[int] = mapped_column(primary_key=True)
    attachment_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("attachments.id", ondelete="CASCADE"),
        nullable=False,
    )
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    viewed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        UniqueConstraint(
            "attachment_id", "token_hash", name="uq_proposal_attachment_views_att_token",
        ),
        Index("ix_proposal_attachment_views_token_hash", "token_hash"),
        Index("ix_proposal_attachment_views_attachment", "attachment_id"),
    )


async def record_attachment_view(
    db: AsyncSession,
    *,
    attachment_id: int,
    token: str,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> None:
    """Idempotently record a public-link view for ``attachment_id``.

    Two concurrent downloads under the same token both pass a naive
    check-then-insert: the second flush raises IntegrityError on the
    UNIQUE(attachment_id, token_hash) constraint, the outer transaction
    rolls back, and the customer sees a 500 + a still-locked sign gate.
    Wrap the insert in a SAVEPOINT so the conflict path is contained
    and the outer txn (any prior reads) survives.
    """
    token_hash = _hash_token(token)
    view = ProposalAttachmentView(
        attachment_id=attachment_id,
        token_hash=token_hash,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    try:
        async with db.begin_nested():
            db.add(view)
    except IntegrityError:
        # Concurrent download under the same token already recorded the
        # view — the SAVEPOINT rollback leaves the outer txn clean and
        # this call is a no-op, which is the documented contract.
        pass


async def get_unviewed_attachment_ids(
    db: AsyncSession,
    *,
    proposal_id: int,
    token: str,
) -> list[int]:
    """Return attachment ids on the proposal that have NOT been viewed under ``token``.

    The accept flow uses this to refuse signing when any document is
    still unread. An empty list means every attached document has been
    opened from the same public link at least once.
    """
    token_hash = _hash_token(token)
    rows = await db.execute(
        select(Attachment.id)
        .where(Attachment.entity_type == "proposals")
        .where(Attachment.entity_id == proposal_id)
    )
    attachment_ids = [r[0] for r in rows.all()]
    if not attachment_ids:
        return []

    viewed = await db.execute(
        select(ProposalAttachmentView.attachment_id)
        .where(ProposalAttachmentView.token_hash == token_hash)
        .where(ProposalAttachmentView.attachment_id.in_(attachment_ids))
    )
    viewed_ids = {r[0] for r in viewed.all()}
    return [aid for aid in attachment_ids if aid not in viewed_ids]
