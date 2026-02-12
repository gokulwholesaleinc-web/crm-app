"""Tests for Stripe Payment Infrastructure.

Validates:
- CRUD operations for payments, products, and stripe customers
- Webhook signature verification logic
- Data scoping (sales_rep can only see own payments)
- Payment service methods
- No mocking - uses real DB operations via in-memory SQLite
"""

import hashlib
import hmac
import json
import time

import pytest
from httpx import AsyncClient

from src.auth.security import get_password_hash, create_access_token
from src.auth.models import User
from src.contacts.models import Contact
from src.companies.models import Company
from src.roles.models import Role, UserRole
from src.payments.models import StripeCustomer, Product, Price, Payment, Subscription
from src.payments.service import PaymentService


# =========================================================================
# Helper fixtures
# =========================================================================

def _token(user: User) -> dict:
    """Create auth headers for a user."""
    token = create_access_token(data={"sub": str(user.id)})
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
async def sales_rep_a(db_session):
    """Create sales rep A user."""
    user = User(
        email="pay_repa@test.com",
        hashed_password=get_password_hash("password123"),
        full_name="Pay Sales Rep A",
        is_active=True,
        is_superuser=False,
        role="sales_rep",
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    role = Role(name="pay_sales_rep_a_role", permissions={
        "payments": ["create", "read", "update", "delete"],
    })
    db_session.add(role)
    await db_session.commit()
    await db_session.refresh(role)

    user_role = UserRole(user_id=user.id, role_id=role.id)
    db_session.add(user_role)
    await db_session.commit()

    return user


@pytest.fixture
async def sales_rep_b(db_session):
    """Create sales rep B user."""
    user = User(
        email="pay_repb@test.com",
        hashed_password=get_password_hash("password123"),
        full_name="Pay Sales Rep B",
        is_active=True,
        is_superuser=False,
        role="sales_rep",
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    role = Role(name="pay_sales_rep_b_role", permissions={
        "payments": ["create", "read", "update", "delete"],
    })
    db_session.add(role)
    await db_session.commit()
    await db_session.refresh(role)

    user_role = UserRole(user_id=user.id, role_id=role.id)
    db_session.add(user_role)
    await db_session.commit()

    return user


@pytest.fixture
async def manager_user(db_session):
    """Create a manager user."""
    user = User(
        email="pay_manager@test.com",
        hashed_password=get_password_hash("password123"),
        full_name="Pay Manager",
        is_active=True,
        is_superuser=False,
        role="manager",
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    role = Role(name="manager", permissions={
        "payments": ["create", "read", "update", "delete"],
    })
    db_session.add(role)
    await db_session.commit()
    await db_session.refresh(role)

    user_role = UserRole(user_id=user.id, role_id=role.id)
    db_session.add(user_role)
    await db_session.commit()

    return user


@pytest.fixture
async def test_stripe_customer(db_session):
    """Create a test Stripe customer."""
    customer = StripeCustomer(
        stripe_customer_id="cus_test_123",
        email="stripe_customer@test.com",
        name="Test Stripe Customer",
    )
    db_session.add(customer)
    await db_session.commit()
    await db_session.refresh(customer)
    return customer


@pytest.fixture
async def test_product(db_session, test_user):
    """Create a test product."""
    product = Product(
        name="Test Product",
        description="A test product",
        stripe_product_id="prod_test_123",
        is_active=True,
        owner_id=test_user.id,
        created_by_id=test_user.id,
    )
    db_session.add(product)
    await db_session.commit()
    await db_session.refresh(product)
    return product


@pytest.fixture
async def test_price(db_session, test_product):
    """Create a test price."""
    price = Price(
        product_id=test_product.id,
        stripe_price_id="price_test_123",
        amount=99.99,
        currency="USD",
        recurring_interval="month",
        is_active=True,
    )
    db_session.add(price)
    await db_session.commit()
    await db_session.refresh(price)
    return price


@pytest.fixture
async def rep_a_payment(db_session, sales_rep_a, test_stripe_customer):
    """Payment owned by sales rep A."""
    payment = Payment(
        stripe_payment_intent_id="pi_rep_a_test",
        amount=100.00,
        currency="USD",
        status="succeeded",
        customer_id=test_stripe_customer.id,
        owner_id=sales_rep_a.id,
        created_by_id=sales_rep_a.id,
    )
    db_session.add(payment)
    await db_session.commit()
    await db_session.refresh(payment)
    return payment


@pytest.fixture
async def rep_b_payment(db_session, sales_rep_b, test_stripe_customer):
    """Payment owned by sales rep B."""
    payment = Payment(
        stripe_payment_intent_id="pi_rep_b_test",
        amount=200.00,
        currency="USD",
        status="pending",
        customer_id=test_stripe_customer.id,
        owner_id=sales_rep_b.id,
        created_by_id=sales_rep_b.id,
    )
    db_session.add(payment)
    await db_session.commit()
    await db_session.refresh(payment)
    return payment


# =========================================================================
# Test Classes
# =========================================================================

class TestPaymentCRUD:
    """Test Payment CRUD operations via API."""

    @pytest.mark.asyncio
    async def test_list_payments_returns_200(
        self, client: AsyncClient, test_user, rep_a_payment, sales_rep_a,
    ):
        """Listing payments should return 200."""
        response = await client.get("/api/payments", headers=_token(test_user))
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert "total" in data
        assert "page" in data

    @pytest.mark.asyncio
    async def test_get_payment_by_id(
        self, client: AsyncClient, test_user, rep_a_payment, sales_rep_a,
    ):
        """Getting a specific payment should return 200 with correct data."""
        # test_user is superuser-like, or use the owner
        response = await client.get(
            f"/api/payments/{rep_a_payment.id}",
            headers=_token(sales_rep_a),
        )
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == rep_a_payment.id
        assert float(data["amount"]) == 100.00
        assert data["status"] == "succeeded"

    @pytest.mark.asyncio
    async def test_get_nonexistent_payment_returns_404(
        self, client: AsyncClient, test_user,
    ):
        """Getting a nonexistent payment should return 404."""
        response = await client.get("/api/payments/99999", headers=_token(test_user))
        assert response.status_code == 404


class TestProductCRUD:
    """Test Product CRUD operations."""

    @pytest.mark.asyncio
    async def test_create_product(self, client: AsyncClient, test_user):
        """Creating a product should return 201."""
        response = await client.post(
            "/api/payments/products",
            json={"name": "New Product", "description": "A new product"},
            headers=_token(test_user),
        )
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "New Product"
        assert data["is_active"] is True

    @pytest.mark.asyncio
    async def test_list_products(
        self, client: AsyncClient, test_user, test_product,
    ):
        """Listing products should return products."""
        response = await client.get(
            "/api/payments/products",
            headers=_token(test_user),
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total"] >= 1
        product_names = [p["name"] for p in data["items"]]
        assert "Test Product" in product_names


class TestStripeCustomer:
    """Test Stripe customer operations."""

    @pytest.mark.asyncio
    async def test_list_customers(
        self, client: AsyncClient, test_user, test_stripe_customer,
    ):
        """Listing Stripe customers should return customers."""
        response = await client.get(
            "/api/payments/customers",
            headers=_token(test_user),
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total"] >= 1

    @pytest.mark.asyncio
    async def test_sync_customer_requires_contact_or_company(
        self, client: AsyncClient, test_user,
    ):
        """Syncing without contact_id or company_id should return 400."""
        response = await client.post(
            "/api/payments/customers/sync",
            json={},
            headers=_token(test_user),
        )
        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_sync_customer_with_contact(
        self, client: AsyncClient, test_user, test_contact,
    ):
        """Syncing a contact should create a Stripe customer."""
        response = await client.post(
            "/api/payments/customers/sync",
            json={"contact_id": test_contact.id},
            headers=_token(test_user),
        )
        assert response.status_code == 201
        data = response.json()
        assert data["contact_id"] == test_contact.id
        assert data["stripe_customer_id"].startswith("local_")  # No Stripe key configured

    @pytest.mark.asyncio
    async def test_sync_customer_idempotent(
        self, client: AsyncClient, test_user, test_contact,
    ):
        """Syncing the same contact twice should return the same customer."""
        resp1 = await client.post(
            "/api/payments/customers/sync",
            json={"contact_id": test_contact.id},
            headers=_token(test_user),
        )
        resp2 = await client.post(
            "/api/payments/customers/sync",
            json={"contact_id": test_contact.id},
            headers=_token(test_user),
        )
        assert resp1.json()["id"] == resp2.json()["id"]


class TestWebhookSignatureVerification:
    """Test webhook HMAC-SHA256 signature verification logic."""

    def test_valid_signature(self):
        """A correctly signed payload should verify."""
        secret = "whsec_test_secret"
        payload = b'{"type":"checkout.session.completed","id":"evt_123"}'
        timestamp = str(int(time.time()))

        signed_payload = f"{timestamp}.".encode() + payload
        signature = hmac.new(
            secret.encode(), signed_payload, hashlib.sha256
        ).hexdigest()

        sig_header = f"t={timestamp},v1={signature}"

        assert PaymentService._verify_webhook_signature(payload, sig_header, secret) is True

    def test_invalid_signature(self):
        """A tampered payload should fail verification."""
        secret = "whsec_test_secret"
        payload = b'{"type":"checkout.session.completed","id":"evt_123"}'
        timestamp = str(int(time.time()))
        sig_header = f"t={timestamp},v1=invalid_signature_hex"

        assert PaymentService._verify_webhook_signature(payload, sig_header, secret) is False

    def test_missing_timestamp(self):
        """Missing timestamp should fail verification."""
        secret = "whsec_test_secret"
        payload = b'{"type":"checkout.session.completed"}'
        sig_header = "v1=somesignature"

        assert PaymentService._verify_webhook_signature(payload, sig_header, secret) is False

    def test_missing_signature(self):
        """Missing v1 signature should fail verification."""
        secret = "whsec_test_secret"
        payload = b'{"type":"checkout.session.completed"}'
        sig_header = "t=12345"

        assert PaymentService._verify_webhook_signature(payload, sig_header, secret) is False

    def test_empty_sig_header(self):
        """Empty sig header should fail."""
        secret = "whsec_test_secret"
        payload = b'{"type":"test"}'

        assert PaymentService._verify_webhook_signature(payload, "", secret) is False


class TestPaymentDataScoping:
    """Test that payment data is properly isolated between sales reps."""

    @pytest.mark.asyncio
    async def test_sales_rep_a_sees_only_own_payments(
        self, client: AsyncClient, sales_rep_a, sales_rep_b,
        rep_a_payment, rep_b_payment,
    ):
        """Sales rep A should only see their own payments."""
        response = await client.get("/api/payments", headers=_token(sales_rep_a))
        assert response.status_code == 200
        data = response.json()
        payment_ids = [p["id"] for p in data["items"]]
        assert rep_a_payment.id in payment_ids
        assert rep_b_payment.id not in payment_ids

    @pytest.mark.asyncio
    async def test_sales_rep_b_sees_only_own_payments(
        self, client: AsyncClient, sales_rep_a, sales_rep_b,
        rep_a_payment, rep_b_payment,
    ):
        """Sales rep B should only see their own payments."""
        response = await client.get("/api/payments", headers=_token(sales_rep_b))
        assert response.status_code == 200
        data = response.json()
        payment_ids = [p["id"] for p in data["items"]]
        assert rep_b_payment.id in payment_ids
        assert rep_a_payment.id not in payment_ids

    @pytest.mark.asyncio
    async def test_sales_rep_cannot_get_other_users_payment(
        self, client: AsyncClient, sales_rep_a, sales_rep_b, rep_b_payment,
    ):
        """Sales rep A should NOT be able to get rep B's payment by ID."""
        response = await client.get(
            f"/api/payments/{rep_b_payment.id}", headers=_token(sales_rep_a),
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_manager_sees_all_payments(
        self, client: AsyncClient, manager_user, sales_rep_a, sales_rep_b,
        rep_a_payment, rep_b_payment,
    ):
        """Manager should see ALL payments regardless of owner."""
        response = await client.get("/api/payments", headers=_token(manager_user))
        assert response.status_code == 200
        data = response.json()
        payment_ids = [p["id"] for p in data["items"]]
        assert rep_a_payment.id in payment_ids
        assert rep_b_payment.id in payment_ids


class TestPaymentServiceDB:
    """Test PaymentService direct database operations."""

    @pytest.mark.asyncio
    async def test_create_payment_via_service(self, db_session, test_user):
        """Create a payment directly via service."""
        from src.payments.schemas import PaymentCreate
        service = PaymentService(db_session)
        payment_data = PaymentCreate(
            amount=500.00,
            currency="USD",
            status="pending",
            owner_id=test_user.id,
        )
        payment = await service.create(payment_data, test_user.id)
        assert payment.id is not None
        assert payment.amount == 500.00
        assert payment.status == "pending"

    @pytest.mark.asyncio
    async def test_get_payment_by_id_via_service(
        self, db_session, test_user, rep_a_payment, sales_rep_a,
    ):
        """Get payment by ID via service."""
        service = PaymentService(db_session)
        payment = await service.get_by_id(rep_a_payment.id)
        assert payment is not None
        assert payment.amount == 100.00

    @pytest.mark.asyncio
    async def test_update_payment_via_service(
        self, db_session, test_user, rep_a_payment, sales_rep_a,
    ):
        """Update a payment via service."""
        from src.payments.schemas import PaymentUpdate
        service = PaymentService(db_session)
        payment = await service.get_by_id(rep_a_payment.id)
        update_data = PaymentUpdate(status="refunded")
        updated = await service.update(payment, update_data, sales_rep_a.id)
        assert updated.status == "refunded"

    @pytest.mark.asyncio
    async def test_delete_payment_via_service(self, db_session, test_user):
        """Delete a payment via service."""
        from src.payments.schemas import PaymentCreate
        service = PaymentService(db_session)
        payment_data = PaymentCreate(
            amount=100.00,
            currency="USD",
            status="pending",
            owner_id=test_user.id,
        )
        payment = await service.create(payment_data, test_user.id)
        payment_id = payment.id
        await service.delete(payment)
        result = await service.get_by_id(payment_id)
        assert result is None

    @pytest.mark.asyncio
    async def test_get_payment_list_with_status_filter(
        self, db_session, sales_rep_a, sales_rep_b,
        rep_a_payment, rep_b_payment,
    ):
        """Filter payments by status."""
        service = PaymentService(db_session)
        succeeded_payments, total = await service.get_list(status="succeeded")
        assert total >= 1
        for p in succeeded_payments:
            assert p.status == "succeeded"

    @pytest.mark.asyncio
    async def test_sync_customer_creates_local_record(self, db_session, test_contact):
        """sync_customer creates a StripeCustomer record."""
        service = PaymentService(db_session)
        customer = await service.sync_customer(contact_id=test_contact.id)
        assert customer.id is not None
        assert customer.contact_id == test_contact.id
        assert customer.stripe_customer_id.startswith("local_")


class TestCheckoutAndPaymentIntent:
    """Test checkout and payment intent creation endpoints."""

    @pytest.mark.asyncio
    async def test_create_checkout_requires_positive_amount(
        self, client: AsyncClient, test_user,
    ):
        """Creating checkout with zero amount should fail."""
        response = await client.post(
            "/api/payments/create-checkout",
            json={
                "amount": 0,
                "currency": "USD",
                "success_url": "http://localhost/success",
                "cancel_url": "http://localhost/cancel",
            },
            headers=_token(test_user),
        )
        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_create_payment_intent_requires_positive_amount(
        self, client: AsyncClient, test_user,
    ):
        """Creating payment intent with zero amount should fail."""
        response = await client.post(
            "/api/payments/create-payment-intent",
            json={"amount": 0, "currency": "USD"},
            headers=_token(test_user),
        )
        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_create_checkout_without_stripe_key_returns_400(
        self, client: AsyncClient, test_user,
    ):
        """Without STRIPE_SECRET_KEY, checkout should return a descriptive error."""
        response = await client.post(
            "/api/payments/create-checkout",
            json={
                "amount": 100.00,
                "currency": "USD",
                "success_url": "http://localhost/success",
                "cancel_url": "http://localhost/cancel",
            },
            headers=_token(test_user),
        )
        assert response.status_code == 400
        assert "Stripe is not configured" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_create_payment_intent_without_stripe_key_returns_400(
        self, client: AsyncClient, test_user,
    ):
        """Without STRIPE_SECRET_KEY, payment intent should return a descriptive error."""
        response = await client.post(
            "/api/payments/create-payment-intent",
            json={"amount": 100.00, "currency": "USD"},
            headers=_token(test_user),
        )
        assert response.status_code == 400
        assert "Stripe is not configured" in response.json()["detail"]


class TestSubscriptionList:
    """Test subscription listing endpoint."""

    @pytest.mark.asyncio
    async def test_list_subscriptions_returns_200(
        self, client: AsyncClient, test_user,
    ):
        """Listing subscriptions should return 200."""
        response = await client.get(
            "/api/payments/subscriptions",
            headers=_token(test_user),
        )
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert "total" in data

    @pytest.mark.asyncio
    async def test_list_subscriptions_with_data(
        self, client: AsyncClient, test_user,
        db_session, test_stripe_customer, test_price,
    ):
        """Listing subscriptions should include created subscriptions."""
        sub = Subscription(
            stripe_subscription_id="sub_test_123",
            customer_id=test_stripe_customer.id,
            price_id=test_price.id,
            status="active",
            cancel_at_period_end=False,
            owner_id=test_user.id,
            created_by_id=test_user.id,
        )
        db_session.add(sub)
        await db_session.commit()

        response = await client.get(
            "/api/payments/subscriptions",
            headers=_token(test_user),
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total"] >= 1
        sub_ids = [s["stripe_subscription_id"] for s in data["items"]]
        assert "sub_test_123" in sub_ids


class TestWebhookEndpoint:
    """Test the webhook endpoint."""

    @pytest.mark.asyncio
    async def test_webhook_without_signature_returns_400(
        self, client: AsyncClient,
    ):
        """Webhook without valid signature should fail."""
        response = await client.post(
            "/api/payments/webhook",
            content=b'{"type":"test"}',
            headers={"content-type": "application/json"},
        )
        assert response.status_code == 400


class TestPaymentsUnauthorized:
    """Test that all payment endpoints require authentication."""

    @pytest.mark.asyncio
    async def test_list_payments_unauthorized(self, client: AsyncClient):
        response = await client.get("/api/payments")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_get_payment_unauthorized(self, client: AsyncClient):
        response = await client.get("/api/payments/1")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_create_checkout_unauthorized(self, client: AsyncClient):
        response = await client.post("/api/payments/create-checkout", json={})
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_create_payment_intent_unauthorized(self, client: AsyncClient):
        response = await client.post("/api/payments/create-payment-intent", json={})
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_list_customers_unauthorized(self, client: AsyncClient):
        response = await client.get("/api/payments/customers")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_sync_customer_unauthorized(self, client: AsyncClient):
        response = await client.post("/api/payments/customers/sync", json={})
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_list_products_unauthorized(self, client: AsyncClient):
        response = await client.get("/api/payments/products")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_create_product_unauthorized(self, client: AsyncClient):
        response = await client.post("/api/payments/products", json={})
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_list_subscriptions_unauthorized(self, client: AsyncClient):
        response = await client.get("/api/payments/subscriptions")
        assert response.status_code == 401
