"""Payment liveness helper semantics."""

from datetime import UTC, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from src.auth.models import User
from src.companies.models import Company
from src.contacts.models import Contact
from src.payments.liveness import (
    live_company_filter,
    live_contact_filter,
    live_owner_id,
)
from src.payments.models import StripeCustomer


@pytest.mark.asyncio
async def test_live_contact_filter_uses_deleted_at_only(
    db_session: AsyncSession,
    test_user: User,
):
    survivor = Contact(
        first_name="Survivor",
        last_name="Contact",
        email="survivor-filter@example.com",
        owner_id=test_user.id,
        created_by_id=test_user.id,
    )
    db_session.add(survivor)
    await db_session.flush()

    live = Contact(
        first_name="Live",
        last_name="Contact",
        email="live-filter@example.com",
        merged_into_id=survivor.id,
        owner_id=test_user.id,
        created_by_id=test_user.id,
    )
    deleted = Contact(
        first_name="Deleted",
        last_name="Contact",
        email="deleted-filter@example.com",
        deleted_at=datetime.now(UTC),
        owner_id=test_user.id,
        created_by_id=test_user.id,
    )
    db_session.add_all([live, deleted])
    await db_session.commit()

    result = await db_session.execute(
        select(Contact.id).where(*live_contact_filter(Contact))
    )
    ids = set(result.scalars().all())

    assert live.id in ids
    assert deleted.id not in ids


@pytest.mark.asyncio
async def test_live_company_filter_requires_non_merged_status_and_no_pointer(
    db_session: AsyncSession,
    test_user: User,
):
    survivor = Company(
        name="Pointer Survivor Liveness Co",
        status="customer",
        owner_id=test_user.id,
        created_by_id=test_user.id,
    )
    db_session.add(survivor)
    await db_session.flush()

    live = Company(
        name="Live Liveness Co",
        status="customer",
        owner_id=test_user.id,
        created_by_id=test_user.id,
    )
    status_merged = Company(
        name="Status Merged Liveness Co",
        status="merged",
        owner_id=test_user.id,
        created_by_id=test_user.id,
    )
    pointer_merged = Company(
        name="Pointer Merged Liveness Co",
        status="customer",
        merged_into_id=survivor.id,
        owner_id=test_user.id,
        created_by_id=test_user.id,
    )
    db_session.add_all([live, status_merged, pointer_merged])
    await db_session.commit()

    result = await db_session.execute(
        select(Company.id).where(*live_company_filter(Company))
    )
    ids = set(result.scalars().all())

    assert live.id in ids
    assert status_merged.id not in ids
    assert pointer_merged.id not in ids


@pytest.mark.asyncio
async def test_live_owner_id_skips_dead_links_and_falls_back_to_live_company(
    db_session: AsyncSession,
    test_user: User,
):
    contact = Contact(
        first_name="Deleted",
        last_name="Owner",
        email="deleted-owner@example.com",
        deleted_at=datetime.now(UTC),
        owner_id=test_user.id,
        created_by_id=test_user.id,
    )
    company = Company(
        name="Fallback Owner Co",
        status="customer",
        owner_id=test_user.id,
        created_by_id=test_user.id,
    )
    db_session.add_all([contact, company])
    await db_session.flush()

    customer = StripeCustomer(
        stripe_customer_id="cus_live_owner_fallback",
        contact_id=contact.id,
        company_id=company.id,
    )
    db_session.add(customer)
    await db_session.commit()
    await db_session.refresh(customer)

    assert live_owner_id(customer) == test_user.id


@pytest.mark.asyncio
async def test_live_owner_id_skips_merged_company(
    db_session: AsyncSession,
    test_user: User,
):
    survivor = Company(
        name="Owner Survivor Co",
        status="customer",
        owner_id=test_user.id,
        created_by_id=test_user.id,
    )
    merged = Company(
        name="Merged Owner Co",
        status="merged",
        owner_id=test_user.id,
        created_by_id=test_user.id,
    )
    db_session.add_all([survivor, merged])
    await db_session.flush()
    merged.merged_into_id = survivor.id

    customer = StripeCustomer(
        stripe_customer_id="cus_merged_owner_skip",
        company_id=merged.id,
    )
    db_session.add(customer)
    await db_session.commit()
    await db_session.refresh(customer)

    assert live_owner_id(customer) is None
