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

    Includes primary email AND send-as aliases so the participant-overlap guard
    in notify_on_email_reply_received doesn't drop users matched via an alias.
    Mirrors GmailConnection.self_addresses but as a DB query rather than a
    property on an already-loaded object.
    """
    from src.integrations.gmail.models import GmailConnection

    result = await db.execute(
        select(GmailConnection.email, GmailConnection.aliases).where(
            GmailConnection.user_id == user_id,
            GmailConnection.revoked_at.is_(None),
        )
    )
    out: list[str] = []
    for row in result:
        if row.email:
            out.append(row.email.lower())
        for a in (row.aliases or []):
            if a:
                out.append(a.lower())
    return out


async def find_user_ids_by_addresses(
    db: AsyncSession, addresses: list[str]
) -> list[int]:
    """Return distinct user_ids whose active Gmail connection (primary or alias) matches any address.

    Filters in Python on the model's ``self_addresses`` property so we don't depend
    on dialect-specific ARRAY operators. ``_AliasArray.impl=JSON`` binds the Python-side
    comparator to JSON regardless of dialect, so ``.overlap()`` raises AttributeError on
    every dialect — including Postgres prod. Connections are bounded (~tens per tenant)
    so loading them all for the per-inbound notify path is fine.

    Match is case-insensitive. Users with revoked connections are excluded.
    """
    if not addresses:
        return []

    from src.integrations.gmail.models import GmailConnection

    lowered = {a.strip().lower() for a in addresses if a}
    if not lowered:
        return []

    result = await db.execute(
        select(GmailConnection).where(GmailConnection.revoked_at.is_(None))
    )
    matched: set[int] = set()
    for conn in result.scalars():
        if conn.self_addresses & lowered:
            matched.add(conn.user_id)
    return list(matched)
