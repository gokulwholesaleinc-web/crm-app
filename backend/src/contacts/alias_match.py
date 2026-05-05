"""Alias-aware contact lookup — stub implementation.

This file will be replaced by a git merge of contact-email-aliases/features
(Worker B's branch) which adds ContactEmailAlias table support. The function
signature is locked by the shared contract in email-link-contract.md.
"""

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession


async def find_contact_id_by_any_email(
    addresses: list[str], db: AsyncSession
) -> tuple[str | None, int | None]:
    """Return ('contacts', id) for the first contact whose primary email matches
    any of the given addresses. Case-insensitive. Returns (None, None) if no match.

    NOTE: this stub only checks Contact.email (no alias table). B's implementation
    also checks contact_email_aliases. Replace by merging contact-email-aliases/features.
    """
    from src.contacts.models import Contact

    if not addresses:
        return None, None

    lowered = [a.lower() for a in addresses if a]
    if not lowered:
        return None, None

    result = await db.execute(
        select(Contact.id)
        .where(
            Contact.deleted_at.is_(None),
            func.lower(Contact.email).in_(lowered),
        )
        .limit(1)
    )
    contact_id = result.scalar_one_or_none()
    if contact_id is not None:
        return "contacts", contact_id

    return None, None
