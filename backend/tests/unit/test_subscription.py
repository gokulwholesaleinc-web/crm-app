"""Tests for subscription/one-time payment type support.

Validates:
- Creating quotes with payment_type one_time and subscription
- Subscription quote requires recurring_interval
- Listing subscriptions
- Getting subscription by ID
- Canceling a subscription
- No mocking - uses real DB operations via in-memory SQLite
"""

import pytest
from httpx import AsyncClient

from src.auth.security import get_password_hash, create_access_token
from src.auth.models import User
from src.payments.models import StripeCustomer, Product, Price, Subscription
from src.payments.service import SubscriptionService
from src.quotes.models import Quote, QuoteLineItem
from src.quotes.schemas import QuoteCreate


# =========================================================================
# Helper fixtures
# =========================================================================

def _token(user: User) -> dict:
    """Create auth headers for a user."""
    token = create_access_token(data={"sub": str(user.id)})
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
async def sub_stripe_customer(db_session):
    """Create a Stripe customer for subscription tests."""
    customer = StripeCustomer(
        stripe_customer_id="cus_sub_test_456",
        email="sub_customer@test.com",
        name="Sub Test Customer",
    )
    db_session.add(customer)
    await db_session.commit()
    await db_session.refresh(customer)
    return customer


@pytest.fixture
async def sub_product(db_session, test_user):
    """Create a product for subscription tests."""
    product = Product(
        name="Sub Test Product",
        description="A subscription test product",
        stripe_product_id="prod_sub_test_456",
        is_active=True,
        owner_id=test_user.id,
        created_by_id=test_user.id,
    )
    db_session.add(product)
    await db_session.commit()
    await db_session.refresh(product)
    return product


@pytest.fixture
async def sub_price(db_session, sub_product):
    """Create a recurring price for subscription tests."""
    price = Price(
        product_id=sub_product.id,
        stripe_price_id="price_sub_test_456",
        amount=49.99,
        currency="USD",
        recurring_interval="month",
        is_active=True,
    )
    db_session.add(price)
    await db_session.commit()
    await db_session.refresh(price)
    return price


@pytest.fixture
async def test_subscription(db_session, test_user, sub_stripe_customer, sub_price):
    """Create a test subscription."""
    sub = Subscription(
        stripe_subscription_id="sub_test_cancel_456",
        customer_id=sub_stripe_customer.id,
        price_id=sub_price.id,
        status="active",
        cancel_at_period_end=False,
        owner_id=test_user.id,
        created_by_id=test_user.id,
    )
    db_session.add(sub)
    await db_session.commit()
    await db_session.refresh(sub)
    return sub


# =========================================================================
# Test Subscription Quote Creation
# =========================================================================

class TestSubscriptionQuoteCreation:
    """Test creating quotes with payment_type."""

    @pytest.mark.asyncio
    async def test_create_one_time_quote(self, client: AsyncClient, test_user):
        """Creating a one-time quote should succeed with default payment_type."""
        response = await client.post(
            "/api/quotes",
            json={
                "title": "One-Time Service Quote",
                "currency": "USD",
                "status": "draft",
                "discount_value": 0,
                "tax_rate": 0,
                "line_items": [
                    {"description": "Consulting service", "quantity": 1, "unit_price": 500},
                ],
            },
            headers=_token(test_user),
        )
        assert response.status_code == 201
        data = response.json()
        assert data["payment_type"] == "one_time"
        assert data["recurring_interval"] is None

    @pytest.mark.asyncio
    async def test_create_subscription_quote(self, client: AsyncClient, test_user):
        """Creating a subscription quote should include payment_type and recurring_interval."""
        response = await client.post(
            "/api/quotes",
            json={
                "title": "Monthly SaaS Quote",
                "currency": "USD",
                "status": "draft",
                "discount_value": 0,
                "tax_rate": 0,
                "payment_type": "subscription",
                "recurring_interval": "monthly",
                "line_items": [
                    {"description": "SaaS license", "quantity": 1, "unit_price": 99.99},
                ],
            },
            headers=_token(test_user),
        )
        assert response.status_code == 201
        data = response.json()
        assert data["payment_type"] == "subscription"
        assert data["recurring_interval"] == "monthly"

    @pytest.mark.asyncio
    async def test_subscription_quote_requires_recurring_interval(
        self, client: AsyncClient, test_user,
    ):
        """Creating a subscription quote without recurring_interval should fail."""
        response = await client.post(
            "/api/quotes",
            json={
                "title": "Invalid Sub Quote",
                "currency": "USD",
                "status": "draft",
                "discount_value": 0,
                "tax_rate": 0,
                "payment_type": "subscription",
                "line_items": [],
            },
            headers=_token(test_user),
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_create_yearly_subscription_quote(self, client: AsyncClient, test_user):
        """Creating a yearly subscription quote should work."""
        response = await client.post(
            "/api/quotes",
            json={
                "title": "Yearly Plan",
                "currency": "USD",
                "status": "draft",
                "discount_value": 0,
                "tax_rate": 0,
                "payment_type": "subscription",
                "recurring_interval": "yearly",
                "line_items": [
                    {"description": "Annual license", "quantity": 1, "unit_price": 999},
                ],
            },
            headers=_token(test_user),
        )
        assert response.status_code == 201
        data = response.json()
        assert data["payment_type"] == "subscription"
        assert data["recurring_interval"] == "yearly"


# =========================================================================
# Test Subscription Listing
# =========================================================================

class TestSubscriptionEndpoints:
    """Test subscription listing, detail, and cancel endpoints."""

    @pytest.mark.asyncio
    async def test_list_subscriptions(
        self, client: AsyncClient, test_user, test_subscription,
    ):
        """Listing subscriptions should include created subscription."""
        response = await client.get(
            "/api/payments/subscriptions",
            headers=_token(test_user),
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total"] >= 1
        sub_ids = [s["stripe_subscription_id"] for s in data["items"]]
        assert "sub_test_cancel_456" in sub_ids

    @pytest.mark.asyncio
    async def test_get_subscription_by_id(
        self, client: AsyncClient, test_user, test_subscription,
    ):
        """Getting a subscription by ID should return correct data."""
        response = await client.get(
            f"/api/payments/subscriptions/{test_subscription.id}",
            headers=_token(test_user),
        )
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == test_subscription.id
        assert data["status"] == "active"
        assert data["stripe_subscription_id"] == "sub_test_cancel_456"

    @pytest.mark.asyncio
    async def test_get_nonexistent_subscription_returns_404(
        self, client: AsyncClient, test_user,
    ):
        """Getting a nonexistent subscription should return 404."""
        response = await client.get(
            "/api/payments/subscriptions/99999",
            headers=_token(test_user),
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_cancel_subscription(
        self, client: AsyncClient, test_user, test_subscription,
    ):
        """Canceling a subscription should set status to canceled."""
        response = await client.post(
            f"/api/payments/subscriptions/{test_subscription.id}/cancel",
            headers=_token(test_user),
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "canceled"
        assert data["cancel_at_period_end"] is True

    @pytest.mark.asyncio
    async def test_cancel_nonexistent_subscription_returns_404(
        self, client: AsyncClient, test_user,
    ):
        """Canceling a nonexistent subscription should return 404."""
        response = await client.post(
            "/api/payments/subscriptions/99999/cancel",
            headers=_token(test_user),
        )
        assert response.status_code == 404


# =========================================================================
# Test SubscriptionService Direct DB Operations
# =========================================================================

class TestSubscriptionServiceDB:
    """Test SubscriptionService direct database operations."""

    @pytest.mark.asyncio
    async def test_cancel_subscription_via_service(
        self, db_session, test_subscription,
    ):
        """Cancel a subscription directly via service."""
        service = SubscriptionService(db_session)
        sub = await service.get_by_id(test_subscription.id)
        assert sub is not None
        assert sub.status == "active"

        cancelled = await service.cancel(sub)
        assert cancelled.status == "canceled"
        assert cancelled.cancel_at_period_end is True

    @pytest.mark.asyncio
    async def test_list_subscriptions_with_status_filter(
        self, db_session, test_subscription,
    ):
        """Filter subscriptions by status."""
        service = SubscriptionService(db_session)
        subs, total = await service.get_list(status="active")
        assert total >= 1
        for s in subs:
            assert s.status == "active"

    @pytest.mark.asyncio
    async def test_list_subscriptions_empty_for_nonexistent_status(
        self, db_session,
    ):
        """Filtering by nonexistent status should return empty list."""
        service = SubscriptionService(db_session)
        subs, total = await service.get_list(status="nonexistent")
        assert total == 0
        assert len(subs) == 0
