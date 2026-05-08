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


async def find_user_ids_by_addresses(
    db: AsyncSession, addresses: list[str]
) -> list[int]:
    """Return distinct user_ids whose active Gmail connection email matches any address.

    Also checks aliases column so send-as aliases resolve to the right user.
    Match is case-insensitive. Users with revoked connections are excluded.
    """
    if not addresses:
        return []

    from sqlalchemy import func as sql_func
    from sqlalchemy import or_
    from sqlalchemy.types import Text

    from src.integrations.gmail.models import GmailConnection

    lowered = [a.strip().lower() for a in addresses if a]

    # Primary email match — works on both SQLite (test) and Postgres (prod)
    primary_match = sql_func.lower(GmailConnection.email).in_(lowered)

    # Alias overlap — Postgres-only: aliases && ARRAY[...]. On SQLite the
    # _AliasArray stores as JSON so we skip the alias branch there.
    try:
        from sqlalchemy.dialects.postgresql import array as pg_array

        alias_match = GmailConnection.aliases.overlap(
            pg_array(lowered, type_=Text)
        )
        where_clause = or_(primary_match, alias_match)
    except (ImportError, AttributeError):
        # AttributeError: _AliasArray degrades to JSON on SQLite so .overlap()
        # is not available on the comparator. Primary-email match is sufficient
        # for tests; prod Postgres gets the full alias coverage.
        where_clause = primary_match

    result = await db.execute(
        select(GmailConnection.user_id)
        .where(
            GmailConnection.revoked_at.is_(None),
            where_clause,
        )
        .distinct()
    )
    return list(result.scalars())
