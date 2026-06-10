"""Shared liveness predicates for payment-owned CRM links."""

from typing import Any


def live_contact_filter(Contact) -> tuple[Any, ...]:
    """SQLAlchemy filters for a contact that may own payment history."""
    return (Contact.deleted_at.is_(None),)


def live_company_filter(Company) -> tuple[Any, ...]:
    """SQLAlchemy filters for a company that may own payment history."""
    return (
        Company.status != "merged",
        Company.merged_into_id.is_(None),
    )


def is_live_contact(contact: Any | None) -> bool:
    """Object-level equivalent of :func:`live_contact_filter`."""
    return contact is not None and contact.deleted_at is None


def is_live_company(company: Any | None) -> bool:
    """Object-level equivalent of :func:`live_company_filter`."""
    return (
        company is not None
        and company.status != "merged"
        and company.merged_into_id is None
    )


def live_owner_id(customer_row: Any | None) -> int | None:
    """Derive an owner from a StripeCustomer's live CRM links only."""
    if customer_row is None:
        return None
    contact = customer_row.contact
    if is_live_contact(contact) and contact.owner_id:
        return contact.owner_id
    company = customer_row.company
    if is_live_company(company) and company.owner_id:
        return company.owner_id
    return None
