"""Tests for payments search functionality.

Validates:
- Payments list with search parameter returns filtered results
- Payments list without search returns all results
"""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.models import User
from src.auth.security import get_password_hash, create_access_token
from src.payments.models import Payment, StripeCustomer


class TestPaymentsSearch:
    """Tests for the payments search endpoint."""

    @pytest.mark.asyncio
    async def test_search_by_customer_name(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_user: User,
    ):
        """Search payments by customer name."""
        # Create a stripe customer
        customer = StripeCustomer(
            stripe_customer_id="cus_search_test_1",
            email="acme@example.com",
            name="Acme Corp",
        )
        db_session.add(customer)
        await db_session.flush()

        # Create a payment linked to the customer
        payment = Payment(
            amount=1500.00,
            currency="USD",
            status="succeeded",
            customer_id=customer.id,
            owner_id=test_user.id,
            created_by_id=test_user.id,
        )
        db_session.add(payment)

        # Create another payment without a customer
        payment2 = Payment(
            amount=2000.00,
            currency="USD",
            status="pending",
            owner_id=test_user.id,
            created_by_id=test_user.id,
        )
        db_session.add(payment2)
        await db_session.commit()

        # Search by customer name
        response = await client.get(
            "/api/payments",
            headers=auth_headers,
            params={"search": "Acme"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["total"] >= 1
        # All returned payments should be linked to a customer named Acme
        for item in data["items"]:
            customer_data = item.get("customer")
            assert customer_data is not None
            assert "Acme" in (customer_data.get("name") or "")

    @pytest.mark.asyncio
    async def test_search_by_customer_email(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_user: User,
    ):
        """Search payments by customer email."""
        customer = StripeCustomer(
            stripe_customer_id="cus_search_email_1",
            email="unique-search@example.com",
            name="Search Email Customer",
        )
        db_session.add(customer)
        await db_session.flush()

        payment = Payment(
            amount=750.00,
            currency="USD",
            status="succeeded",
            customer_id=customer.id,
            owner_id=test_user.id,
            created_by_id=test_user.id,
        )
        db_session.add(payment)
        await db_session.commit()

        response = await client.get(
            "/api/payments",
            headers=auth_headers,
            params={"search": "unique-search"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["total"] >= 1

    @pytest.mark.asyncio
    async def test_search_by_status(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_user: User,
    ):
        """Search payments by status keyword."""
        payment = Payment(
            amount=300.00,
            currency="USD",
            status="refunded",
            owner_id=test_user.id,
            created_by_id=test_user.id,
        )
        db_session.add(payment)
        await db_session.commit()

        response = await client.get(
            "/api/payments",
            headers=auth_headers,
            params={"search": "refund"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["total"] >= 1
        assert any(item["status"] == "refunded" for item in data["items"])

    @pytest.mark.asyncio
    async def test_search_returns_empty_for_no_match(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_user: User,
    ):
        """Search with no matching term returns empty results."""
        payment = Payment(
            amount=100.00,
            currency="USD",
            status="succeeded",
            owner_id=test_user.id,
            created_by_id=test_user.id,
        )
        db_session.add(payment)
        await db_session.commit()

        response = await client.get(
            "/api/payments",
            headers=auth_headers,
            params={"search": "zzzznonexistentzzzz"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 0
        assert data["items"] == []

    @pytest.mark.asyncio
    async def test_list_without_search_returns_all(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_user: User,
    ):
        """Payments list without search returns all payments."""
        for i in range(3):
            payment = Payment(
                amount=(i + 1) * 100.0,
                currency="USD",
                status="succeeded",
                owner_id=test_user.id,
                created_by_id=test_user.id,
            )
            db_session.add(payment)
        await db_session.commit()

        response = await client.get(
            "/api/payments",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["total"] >= 3
