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
from src.auth.models import User
from src.auth.security import create_access_token
from src.payments.models import Price, Product, StripeCustomer, Subscription
from src.payments.service import SubscriptionService

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

# Quote-creation tests retired 2026-05-14 with the quotes router unmount —
# subscription terms now live on proposals + Stripe directly.


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
