"""Alias-aware contact lookup used by Gmail sync and Resend webhook ingestion."""

from sqlalchemy import func, select, union_all
from sqlalchemy.ext.asyncio import AsyncSession


async def find_contact_id_by_any_email(
    addresses: list[str], db: AsyncSession
) -> tuple[str | None, int | None]:
    """Return ('contacts', id) for the first contact whose primary email OR
    any contact_email_aliases.email row matches any of the given addresses.
    Case-insensitive. Returns (None, None) if no match.

    Skips soft-deleted contacts (deleted_at IS NULL) so a merged-away
    contact doesn't capture mail meant for the surviving record.
    """
    from src.contacts.models import Contact, ContactEmailAlias

    if not addresses:
        return None, None

    lowered = [a.lower() for a in addresses if a]
    if not lowered:
        return None, None

    # Build a UNION across the primary email column and alias table. Both
    # branches return (contact_id, matched_email) so the outer query can
    # pick the first hit in input-list order.
    primary_q = (
        select(Contact.id.label("contact_id"), func.lower(Contact.email).label("matched"))
        .where(
            Contact.deleted_at.is_(None),
            func.lower(Contact.email).in_(lowered),
        )
    )
    alias_q = (
        select(
            ContactEmailAlias.contact_id.label("contact_id"),
            func.lower(ContactEmailAlias.email).label("matched"),
        )
        .join(Contact, Contact.id == ContactEmailAlias.contact_id)
        .where(
            Contact.deleted_at.is_(None),
            func.lower(ContactEmailAlias.email).in_(lowered),
        )
    )

    combined = union_all(primary_q, alias_q).subquery()
    result = await db.execute(select(combined.c.contact_id, combined.c.matched))
    rows = result.all()

    if not rows:
        return None, None

    # Preserve input-list order: pick the match whose address appears
    # earliest in the caller-supplied list.
    by_email: dict[str, int] = {row.matched: row.contact_id for row in rows}
    for addr in lowered:
        if addr in by_email:
            return "contacts", by_email[addr]

    return None, None
