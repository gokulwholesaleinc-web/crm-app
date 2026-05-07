"""Happy-path sort tests for the 5 list endpoints.

Each test seeds a known minimum dataset, calls the endpoint with a
specific (order_by, order_dir), and asserts that the first item in the
response matches what that ordering predicts. Allowlist coverage and
SQL-injection guard live implicitly: any value not in the per-entity
allowlist falls back to default ordering, and unknown directions are
coerced to 'desc' (see src/core/sorting.py).
"""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.models import User
from src.contacts.models import Contact
from src.leads.models import Lead, LeadSource
from src.payments.models import Payment, StripeCustomer
from src.proposals.models import Proposal
from src.quotes.models import Quote


class TestContactsSort:
    """Contacts list endpoint honors order_by=email&order_dir=asc."""

    @pytest.mark.asyncio
    async def test_sort_by_email_asc(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_user: User,
    ):
        """Should return contacts ordered by email ascending."""
        emails = ["zebra@example.com", "alpha@example.com", "mango@example.com"]
        for i, email in enumerate(emails):
            db_session.add(
                Contact(
                    first_name=f"First{i}",
                    last_name=f"Last{i}",
                    email=email,
                    status="active",
                    owner_id=test_user.id,
                    created_by_id=test_user.id,
                )
            )
        await db_session.commit()

        response = await client.get(
            "/api/contacts",
            headers=auth_headers,
            params={"order_by": "email", "order_dir": "asc", "page_size": 10},
        )
        assert response.status_code == 200
        items = response.json()["items"]
        returned_emails = [c["email"] for c in items if c["email"] in emails]
        assert returned_emails == sorted(emails)


class TestLeadsSort:
    """Leads list endpoint honors order_by=score&order_dir=desc."""

    @pytest.mark.asyncio
    async def test_sort_by_score_desc(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_user: User,
        test_lead_source: LeadSource,
    ):
        """Should return leads ordered by score descending."""
        scores = [25, 95, 60]
        for i, score in enumerate(scores):
            db_session.add(
                Lead(
                    first_name=f"L{i}",
                    last_name=f"Score{score}",
                    email=f"lead{i}@example.com",
                    source_id=test_lead_source.id,
                    status="new",
                    score=score,
                    owner_id=test_user.id,
                    created_by_id=test_user.id,
                )
            )
        await db_session.commit()

        response = await client.get(
            "/api/leads",
            headers=auth_headers,
            params={"order_by": "score", "order_dir": "desc", "page_size": 10},
        )
        assert response.status_code == 200
        items = response.json()["items"]
        returned_scores = [l["score"] for l in items if l["score"] in scores]
        assert returned_scores == sorted(scores, reverse=True)


class TestQuotesSort:
    """Quotes list endpoint honors order_by=total&order_dir=desc."""

    @pytest.mark.asyncio
    async def test_sort_by_total_desc(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_user: User,
    ):
        """Should return quotes ordered by total descending."""
        totals = [100.00, 999.99, 250.50]
        for i, total in enumerate(totals):
            db_session.add(
                Quote(
                    quote_number=f"QT-TEST-{i:04d}",
                    public_token=f"tok-test-quote-sort-{i}-aaaaaaaaaaaaaaaa",
                    title=f"Quote {i}",
                    status="draft",
                    payment_type="one_time",
                    currency="USD",
                    subtotal=total,
                    tax_rate=0,
                    tax_amount=0,
                    total=total,
                    owner_id=test_user.id,
                    created_by_id=test_user.id,
                )
            )
        await db_session.commit()

        response = await client.get(
            "/api/quotes",
            headers=auth_headers,
            params={"order_by": "total", "order_dir": "desc", "page_size": 10},
        )
        assert response.status_code == 200
        items = response.json()["items"]
        returned_totals = [float(q["total"]) for q in items if float(q["total"]) in totals]
        assert returned_totals == sorted(totals, reverse=True)


class TestProposalsSort:
    """Proposals list endpoint honors order_by=view_count&order_dir=desc."""

    @pytest.mark.asyncio
    async def test_sort_by_view_count_desc(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_user: User,
    ):
        """Should return proposals ordered by view_count descending."""
        view_counts = [3, 17, 8]
        for i, vc in enumerate(view_counts):
            db_session.add(
                Proposal(
                    proposal_number=f"PR-TEST-{i:04d}",
                    public_token=f"tok-test-proposal-sort-{i}-aaaaaaaaaaaaa",
                    title=f"Proposal {i}",
                    status="draft",
                    payment_type="one_time",
                    currency="USD",
                    view_count=vc,
                    owner_id=test_user.id,
                    created_by_id=test_user.id,
                )
            )
        await db_session.commit()

        response = await client.get(
            "/api/proposals",
            headers=auth_headers,
            params={"order_by": "view_count", "order_dir": "desc", "page_size": 10},
        )
        assert response.status_code == 200
        items = response.json()["items"]
        returned = [p["view_count"] for p in items if p["view_count"] in view_counts]
        assert returned == sorted(view_counts, reverse=True)


class TestPaymentsSort:
    """Payments list endpoint honors order_by=amount&order_dir=desc."""

    @pytest.mark.asyncio
    async def test_sort_by_amount_desc(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_user: User,
    ):
        """Should return payments ordered by amount descending."""
        customer = StripeCustomer(
            stripe_customer_id="cus_test_sort",
            email="cust@example.com",
            name="Sort Test Customer",
        )
        db_session.add(customer)
        await db_session.commit()
        await db_session.refresh(customer)

        amounts = [50.00, 500.00, 150.00]
        for i, amt in enumerate(amounts):
            db_session.add(
                Payment(
                    stripe_payment_intent_id=f"pi_test_sort_{i}",
                    customer_id=customer.id,
                    amount=amt,
                    currency="USD",
                    status="succeeded",
                    owner_id=test_user.id,
                    created_by_id=test_user.id,
                )
            )
        await db_session.commit()

        response = await client.get(
            "/api/payments",
            headers=auth_headers,
            params={"order_by": "amount", "order_dir": "desc", "page_size": 10},
        )
        assert response.status_code == 200
        items = response.json()["items"]
        returned = [float(p["amount"]) for p in items if float(p["amount"]) in amounts]
        assert returned == sorted(amounts, reverse=True)
