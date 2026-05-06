"""Helpers for extracting and matching email participant addresses.

The participant set is the lowercased + deduped union of bare addresses
from a message's From/To/CC/BCC headers, persisted on InboundEmail and
EmailQueue rows so visibility queries can scope by overlap with the
viewing user's connected Gmail addresses.
"""

from email.utils import getaddresses

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


def collect_participants(*headers: str | None) -> list[str]:
    """Pull bare addresses from one or more From/To/CC/BCC header strings.

    Uses RFC 5322-aware parsing so display names like ``"Foo" <foo@bar>``
    are stripped. Result is sorted, lowercased, deduped.
    """
    pairs = getaddresses([h for h in headers if h])
    return sorted({addr.strip().lower() for _, addr in pairs if addr and "@" in addr})


async def get_user_connection_emails(db: AsyncSession, user_id: int) -> list[str]:
    """Return all active Gmail connection addresses for a user, lowercased.

    Used as the membership set for participant-overlap visibility queries.
    A user with no connection sees nothing scoped this way; outbound rows
    they composed themselves remain visible via the ``sent_by_id`` branch.
    """
    from src.integrations.gmail.models import GmailConnection

    result = await db.execute(
        select(GmailConnection.email).where(
            GmailConnection.user_id == user_id,
            GmailConnection.revoked_at.is_(None),
        )
    )
    return [e.lower() for e in result.scalars()]
