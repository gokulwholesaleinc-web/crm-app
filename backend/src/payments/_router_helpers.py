"""Shared auth/access helpers for payments sub-routers (private module)."""

from fastapi import HTTPException
from sqlalchemy import select

from src.core.constants import HTTPStatus
from src.core.router_utils import raise_forbidden
from src.payments.models import StripeCustomer


def _is_privileged(current_user) -> bool:
    """Admin/manager/superuser bypass ownership checks in this module."""
    if current_user.is_superuser:
        return True
    return getattr(current_user, "role", "sales_rep") in ("admin", "manager")


async def _verify_contact_access(db, contact_id: int | None, current_user) -> None:
    """Raise 403 if the caller cannot access the referenced contact.

    Soft-deleted rows (``deleted_at IS NOT NULL``) are treated as missing
    so the caller gets 404 instead of being able to probe for existence
    through the helper. Without this filter, a deleted contact passes
    the existence check and the ownership branch decides 403 vs.
    proceed — the same fabricated-empty-result oracle the caller is
    trying to close.
    """
    if contact_id is None or _is_privileged(current_user):
        return
    from src.contacts.models import Contact
    result = await db.execute(
        select(Contact).where(
            Contact.id == contact_id,
            Contact.deleted_at.is_(None),
        )
    )
    contact = result.scalar_one_or_none()
    if contact is None:
        raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail="Contact not found")
    if contact.owner_id != current_user.id:
        raise_forbidden("You do not have permission to reference this contact")


async def _verify_company_access(db, company_id: int | None, current_user) -> None:
    """Raise 403 if the caller cannot access the referenced company."""
    if company_id is None or _is_privileged(current_user):
        return
    from src.companies.models import Company
    result = await db.execute(select(Company).where(Company.id == company_id))
    company = result.scalar_one_or_none()
    if company is None:
        raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail="Company not found")
    if company.owner_id != current_user.id:
        raise_forbidden("You do not have permission to reference this company")


async def _verify_quote_access(db, quote_id: int | None, current_user) -> None:
    """Raise 403 if the caller cannot access the referenced quote."""
    if quote_id is None or _is_privileged(current_user):
        return
    from src.quotes.models import Quote
    result = await db.execute(select(Quote).where(Quote.id == quote_id))
    quote = result.scalar_one_or_none()
    if quote is None:
        raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail="Quote not found")
    if quote.owner_id != current_user.id:
        raise_forbidden("You do not have permission to reference this quote")


async def _verify_opportunity_access(db, opportunity_id: int | None, current_user) -> None:
    """Raise 403 if the caller cannot access the referenced opportunity."""
    if opportunity_id is None or _is_privileged(current_user):
        return
    from src.opportunities.models import Opportunity
    result = await db.execute(select(Opportunity).where(Opportunity.id == opportunity_id))
    opp = result.scalar_one_or_none()
    if opp is None:
        raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail="Opportunity not found")
    if opp.owner_id != current_user.id:
        raise_forbidden("You do not have permission to reference this opportunity")


async def _verify_stripe_customer_access(db, stripe_customer_id: int, current_user) -> StripeCustomer:
    """Load a StripeCustomer and raise 403 unless caller owns the linked contact/company.

    StripeCustomer has no `owner_id` column itself, so access is derived from
    whichever CRM entity (contact or company) it points at.
    """
    result = await db.execute(
        select(StripeCustomer).where(StripeCustomer.id == stripe_customer_id)
    )
    sc = result.scalar_one_or_none()
    if sc is None:
        raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail="Stripe customer not found")
    if _is_privileged(current_user):
        return sc
    owner_ids = {
        sc.contact.owner_id if sc.contact else None,
        sc.company.owner_id if sc.company else None,
    }
    owner_ids.discard(None)
    if current_user.id not in owner_ids:
        raise_forbidden("You do not have permission to use this Stripe customer")
    return sc
