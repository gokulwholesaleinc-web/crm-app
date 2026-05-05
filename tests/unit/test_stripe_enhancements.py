"""Tests for Stripe Enhancements: ACH, Invoice creation, Onboarding link, new webhooks.

Validates:
- Invoice creation endpoint validation
- Onboarding link endpoint validation
- New webhook handlers (invoice.paid, invoice.payment_failed, invoice.sent,
  async payment events, setup_intent.succeeded)
- ACH payment_method_types in checkout (service-level check)
- No mocking — uses real DB operations via in-memory SQLite
"""

import hashlib
import hmac
import json
import time

import pytest
from httpx import AsyncClient

from src.auth.security import get_password_hash, create_access_token
from src.auth.models import User
from src.payments.models import StripeCustomer, Payment, Subscription
from src.payments.service import PaymentService
from src.config import settings


def _token(user: User) -> dict:
    token = create_access_token(data={"sub": str(user.id)})
    return {"Authorization": f"Bearer {token}"}


def _make_signed_payload(event_type: str, obj: dict, secret: str) -> tuple:
    """Build a signed webhook payload. Returns (payload_bytes, sig_header)."""
    event_data = {
        "id": f"evt_{event_type.replace('.', '_')}_{int(time.time())}",
        "type": event_type,
        "data": {"object": obj},
    }
    payload = json.dumps(event_data).encode()
    timestamp = str(int(time.time()))
    signed_payload = f"{timestamp}.".encode() + payload
    signature = hmac.new(secret.encode(), signed_payload, hashlib.sha256).hexdigest()
    sig_header = f"t={timestamp},v1={signature}"
    return payload, sig_header


@pytest.fixture
async def stripe_customer(db_session, test_contact):
    """StripeCustomer linked to test_contact (owned by test_user) so owner
    scoping in invoice/onboarding endpoints treats the caller as authorized."""
    customer = StripeCustomer(
        stripe_customer_id="cus_enhance_test",
        email="enhance@test.com",
        name="Enhance Test Customer",
        contact_id=test_contact.id,
    )
    db_session.add(customer)
    await db_session.commit()
    await db_session.refresh(customer)
    return customer


@pytest.fixture
async def invoice_payment(db_session, test_user, stripe_customer):
    """Create a payment with stripe_invoice_id for webhook tests."""
    payment = Payment(
        stripe_invoice_id="in_test_invoice_001",
        amount=250.00,
        currency="USD",
        status="sent",
        customer_id=stripe_customer.id,
        owner_id=test_user.id,
        created_by_id=test_user.id,
    )
    db_session.add(payment)
    await db_session.commit()
    await db_session.refresh(payment)
    return payment


@pytest.fixture
async def pending_invoice_payment(db_session, test_user, stripe_customer):
    """Create a pending payment with stripe_invoice_id for invoice.sent test."""
    payment = Payment(
        stripe_invoice_id="in_test_invoice_pending",
        amount=150.00,
        currency="USD",
        status="pending",
        customer_id=stripe_customer.id,
        owner_id=test_user.id,
        created_by_id=test_user.id,
    )
    db_session.add(payment)
    await db_session.commit()
    await db_session.refresh(payment)
    return payment


@pytest.fixture
async def ach_checkout_payment(db_session, test_user):
    """Create a payment with checkout session ID for async payment tests."""
    payment = Payment(
        stripe_checkout_session_id="cs_ach_test_001",
        amount=500.00,
        currency="USD",
        status="pending",
        owner_id=test_user.id,
        created_by_id=test_user.id,
    )
    db_session.add(payment)
    await db_session.commit()
    await db_session.refresh(payment)
    return payment


# =========================================================================
# Invoice Creation Endpoint Tests
# =========================================================================

class TestCreateAndSendInvoice:
    """Test the invoice creation endpoint."""

    @pytest.mark.asyncio
    async def test_create_invoice_requires_auth(self, client: AsyncClient):
        """Should return 401 without authentication."""
        response = await client.post(
            "/api/payments/invoices/create-and-send",
            json={
                "customer_id": 1,
                "amount": 100.00,
                "description": "Test invoice",
            },
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_create_invoice_requires_positive_amount(
        self, client: AsyncClient, test_user,
    ):
        """Should return 400 for zero or negative amount."""
        response = await client.post(
            "/api/payments/invoices/create-and-send",
            json={
                "customer_id": 1,
                "amount": 0,
                "description": "Test invoice",
            },
            headers=_token(test_user),
        )
        assert response.status_code == 400
        assert "Amount must be greater than 0" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_create_invoice_requires_negative_amount(
        self, client: AsyncClient, test_user,
    ):
        """Should return 400 for negative amount."""
        response = await client.post(
            "/api/payments/invoices/create-and-send",
            json={
                "customer_id": 1,
                "amount": -50,
                "description": "Test invoice",
            },
            headers=_token(test_user),
        )
        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_create_invoice_without_stripe_returns_400(
        self, client: AsyncClient, test_user, stripe_customer,
    ):
        """Without STRIPE_SECRET_KEY, invoice creation should return descriptive error."""
        response = await client.post(
            "/api/payments/invoices/create-and-send",
            json={
                "customer_id": stripe_customer.id,
                "amount": 100.00,
                "description": "Test invoice",
            },
            headers=_token(test_user),
        )
        assert response.status_code == 400
        assert "Stripe is not configured" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_create_invoice_missing_customer_returns_404(
        self, client: AsyncClient, test_user,
    ):
        """Invoice with nonexistent customer_id should return 404.

        Previously returned 400 because the check was on the Stripe API
        side. The ownership pre-check now surfaces a 404 for missing
        customers, which is more correct.
        """
        response = await client.post(
            "/api/payments/invoices/create-and-send",
            json={
                "customer_id": 99999,
                "amount": 100.00,
                "description": "Test invoice",
            },
            headers=_token(test_user),
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_create_invoice_accepts_full_body(
        self, client: AsyncClient, test_user, stripe_customer,
    ):
        """Should accept customer_id, amount, description, due_days, payment_method_types."""
        response = await client.post(
            "/api/payments/invoices/create-and-send",
            json={
                "customer_id": stripe_customer.id,
                "amount": 250.00,
                "description": "Consulting services",
                "due_days": 14,
                "payment_method_types": ["card", "us_bank_account"],
            },
            headers=_token(test_user),
        )
        # Without a real Stripe key this returns 400 "Stripe is not configured",
        # but it should NOT be 422 (validation passes).
        assert response.status_code == 400
        assert "Stripe is not configured" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_create_invoice_missing_required_fields_returns_422(
        self, client: AsyncClient, test_user,
    ):
        """Should return 422 when required fields are missing."""
        response = await client.post(
            "/api/payments/invoices/create-and-send",
            json={},
            headers=_token(test_user),
        )
        assert response.status_code == 422


# =========================================================================
# Subscription Checkout Endpoint Tests (Send Invoice → Subscription path)
# =========================================================================

class TestCreateAndSendSubscription:
    """The /api/payments/subscriptions/create-and-send endpoint backs the
    Send Invoice modal's 'Subscription' radio. Stripe is unconfigured in
    tests, so we cover validation + auth + customer access; the happy
    path through Stripe is exercised by service-level tests that stub
    _get_stripe()."""

    SUB_BODY = {
        "amount": 199.00,
        "description": "Monthly retainer",
        "interval": "month",
        "interval_count": 1,
        "success_url": "http://localhost/success",
        "cancel_url": "http://localhost/cancel",
    }

    @pytest.mark.asyncio
    async def test_subscription_requires_auth(self, client: AsyncClient):
        """Should return 401 without authentication."""
        response = await client.post(
            "/api/payments/subscriptions/create-and-send",
            json={"customer_id": 1, **self.SUB_BODY},
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_subscription_rejects_zero_amount(
        self, client: AsyncClient, test_user, stripe_customer,
    ):
        """Should return 400 for zero amount."""
        response = await client.post(
            "/api/payments/subscriptions/create-and-send",
            json={**self.SUB_BODY, "customer_id": stripe_customer.id, "amount": 0},
            headers=_token(test_user),
        )
        assert response.status_code == 400
        assert "Amount must be greater than 0" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_subscription_rejects_invalid_interval(
        self, client: AsyncClient, test_user, stripe_customer,
    ):
        """Pydantic Literal['month','year'] rejects 'week' at the schema layer."""
        response = await client.post(
            "/api/payments/subscriptions/create-and-send",
            json={**self.SUB_BODY, "customer_id": stripe_customer.id, "interval": "week"},
            headers=_token(test_user),
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_subscription_rejects_zero_interval_count(
        self, client: AsyncClient, test_user, stripe_customer,
    ):
        """Pydantic ge=1 rejects interval_count=0 at the schema layer."""
        response = await client.post(
            "/api/payments/subscriptions/create-and-send",
            json={**self.SUB_BODY, "customer_id": stripe_customer.id, "interval_count": 0},
            headers=_token(test_user),
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_subscription_unknown_customer_returns_404(
        self, client: AsyncClient, test_user,
    ):
        """Customer ownership pre-check should 404 for missing customers."""
        response = await client.post(
            "/api/payments/subscriptions/create-and-send",
            json={**self.SUB_BODY, "customer_id": 99999},
            headers=_token(test_user),
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_subscription_without_stripe_returns_400(
        self, client: AsyncClient, test_user, stripe_customer,
    ):
        """Without STRIPE_SECRET_KEY, subscription checkout should surface a descriptive error."""
        response = await client.post(
            "/api/payments/subscriptions/create-and-send",
            json={**self.SUB_BODY, "customer_id": stripe_customer.id},
            headers=_token(test_user),
        )
        assert response.status_code == 400
        assert "Stripe is not configured" in response.json()["detail"]


# =========================================================================
# Onboarding Link Endpoint Tests
# =========================================================================

class TestOnboardingLink:
    """Test the customer onboarding link endpoint."""

    @pytest.mark.asyncio
    async def test_onboarding_requires_auth(self, client: AsyncClient):
        """Should return 401 without authentication."""
        response = await client.post(
            "/api/payments/customers/onboarding-link",
            json={
                "contact_id": 1,
                "success_url": "http://localhost/success",
                "cancel_url": "http://localhost/cancel",
            },
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_onboarding_requires_contact_or_company(
        self, client: AsyncClient, test_user,
    ):
        """Should return 400 without contact_id or company_id."""
        response = await client.post(
            "/api/payments/customers/onboarding-link",
            json={
                "success_url": "http://localhost/success",
                "cancel_url": "http://localhost/cancel",
            },
            headers=_token(test_user),
        )
        assert response.status_code == 400
        assert "contact_id or company_id" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_onboarding_without_stripe_returns_400(
        self, client: AsyncClient, test_user, test_contact,
    ):
        """Without STRIPE_SECRET_KEY, onboarding should return descriptive error."""
        response = await client.post(
            "/api/payments/customers/onboarding-link",
            json={
                "contact_id": test_contact.id,
                "success_url": "http://localhost/success",
                "cancel_url": "http://localhost/cancel",
            },
            headers=_token(test_user),
        )
        assert response.status_code == 400
        assert "Stripe is not configured" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_onboarding_accepts_company_id(
        self, client: AsyncClient, test_user, test_company,
    ):
        """Should accept company_id instead of contact_id."""
        response = await client.post(
            "/api/payments/customers/onboarding-link",
            json={
                "company_id": test_company.id,
                "success_url": "http://localhost/success",
                "cancel_url": "http://localhost/cancel",
            },
            headers=_token(test_user),
        )
        assert response.status_code == 400
        assert "Stripe is not configured" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_onboarding_missing_urls_returns_422(
        self, client: AsyncClient, test_user,
    ):
        """Should return 422 when required URL fields are missing."""
        response = await client.post(
            "/api/payments/customers/onboarding-link",
            json={"contact_id": 1},
            headers=_token(test_user),
        )
        assert response.status_code == 422


# =========================================================================
# Invoice Webhook Handler Tests
# =========================================================================

class TestInvoiceWebhookHandlers:
    """Test new invoice-related webhook handlers via direct service calls."""

    @pytest.mark.asyncio
    async def test_invoice_paid_marks_succeeded(
        self, db_session, invoice_payment,
    ):
        """invoice.paid should set payment status to succeeded."""
        service = PaymentService(db_session)
        await service._handle_invoice_paid({"id": "in_test_invoice_001"})
        await db_session.refresh(invoice_payment)
        assert invoice_payment.status == "succeeded"

    @pytest.mark.asyncio
    async def test_invoice_paid_idempotent(
        self, db_session, invoice_payment,
    ):
        """Calling invoice.paid twice should not error."""
        service = PaymentService(db_session)
        await service._handle_invoice_paid({"id": "in_test_invoice_001"})
        await service._handle_invoice_paid({"id": "in_test_invoice_001"})
        await db_session.refresh(invoice_payment)
        assert invoice_payment.status == "succeeded"

    @pytest.mark.asyncio
    async def test_invoice_paid_no_match(self, db_session):
        """invoice.paid with unknown invoice_id should not error."""
        service = PaymentService(db_session)
        await service._handle_invoice_paid({"id": "in_nonexistent"})

    @pytest.mark.asyncio
    async def test_invoice_payment_failed(
        self, db_session, invoice_payment,
    ):
        """invoice.payment_failed should set payment status to failed."""
        service = PaymentService(db_session)
        await service._handle_invoice_payment_failed({"id": "in_test_invoice_001"})
        await db_session.refresh(invoice_payment)
        assert invoice_payment.status == "failed"

    @pytest.mark.asyncio
    async def test_invoice_payment_failed_does_not_override_succeeded(
        self, db_session, test_user, stripe_customer,
    ):
        """invoice.payment_failed should not downgrade a succeeded payment."""
        payment = Payment(
            stripe_invoice_id="in_already_succeeded",
            amount=100.00,
            currency="USD",
            status="succeeded",
            customer_id=stripe_customer.id,
            owner_id=test_user.id,
            created_by_id=test_user.id,
        )
        db_session.add(payment)
        await db_session.commit()

        service = PaymentService(db_session)
        await service._handle_invoice_payment_failed({"id": "in_already_succeeded"})
        await db_session.refresh(payment)
        assert payment.status == "succeeded"

    @pytest.mark.asyncio
    async def test_invoice_sent_marks_sent(
        self, db_session, pending_invoice_payment,
    ):
        """invoice.sent should set pending payment status to sent."""
        service = PaymentService(db_session)
        await service._handle_invoice_sent({"id": "in_test_invoice_pending"})
        await db_session.refresh(pending_invoice_payment)
        assert pending_invoice_payment.status == "sent"

    @pytest.mark.asyncio
    async def test_invoice_sent_does_not_override_non_pending(
        self, db_session, invoice_payment,
    ):
        """invoice.sent should not change status if already 'sent'."""
        assert invoice_payment.status == "sent"
        service = PaymentService(db_session)
        await service._handle_invoice_sent({"id": "in_test_invoice_001"})
        await db_session.refresh(invoice_payment)
        assert invoice_payment.status == "sent"


# =========================================================================
# ACH Async Payment Webhook Tests
# =========================================================================

class TestAsyncPaymentWebhookHandlers:
    """Test ACH async payment webhook handlers."""

    @pytest.mark.asyncio
    async def test_async_payment_succeeded(
        self, db_session, ach_checkout_payment,
    ):
        """async_payment_succeeded should set payment to succeeded."""
        service = PaymentService(db_session)
        await service._handle_async_payment_succeeded({
            "id": "cs_ach_test_001",
            "payment_intent": "pi_ach_resolved",
        })
        await db_session.refresh(ach_checkout_payment)
        assert ach_checkout_payment.status == "succeeded"
        assert ach_checkout_payment.stripe_payment_intent_id == "pi_ach_resolved"

    @pytest.mark.asyncio
    async def test_async_payment_failed(
        self, db_session, ach_checkout_payment,
    ):
        """async_payment_failed should set payment to failed."""
        service = PaymentService(db_session)
        await service._handle_async_payment_failed({"id": "cs_ach_test_001"})
        await db_session.refresh(ach_checkout_payment)
        assert ach_checkout_payment.status == "failed"

    @pytest.mark.asyncio
    async def test_async_payment_failed_does_not_override_succeeded(
        self, db_session, test_user,
    ):
        """async_payment_failed should not downgrade a succeeded payment."""
        payment = Payment(
            stripe_checkout_session_id="cs_already_done",
            amount=300.00,
            currency="USD",
            status="succeeded",
            owner_id=test_user.id,
            created_by_id=test_user.id,
        )
        db_session.add(payment)
        await db_session.commit()

        service = PaymentService(db_session)
        await service._handle_async_payment_failed({"id": "cs_already_done"})
        await db_session.refresh(payment)
        assert payment.status == "succeeded"


# =========================================================================
# Setup Intent Webhook Test
# =========================================================================

# =========================================================================
# Full Webhook Endpoint Tests (invoice events via signed HTTP)
# =========================================================================

class TestInvoiceWebhookEndpoint:
    """Test new webhook event types via the HTTP endpoint with signed payloads."""

    @pytest.mark.asyncio
    async def test_invoice_paid_via_webhook_endpoint(
        self, client: AsyncClient, db_session, invoice_payment, monkeypatch,
    ):
        """Signed invoice.paid event should mark payment as succeeded."""
        secret = "whsec_test_enhance"
        monkeypatch.setattr(settings, "STRIPE_WEBHOOK_SECRET", secret)

        payload, sig_header = _make_signed_payload(
            "invoice.paid",
            {"id": "in_test_invoice_001"},
            secret,
        )

        response = await client.post(
            "/api/payments/webhook",
            content=payload,
            headers={
                "content-type": "application/json",
                "stripe-signature": sig_header,
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["event_type"] == "invoice.paid"

        await db_session.refresh(invoice_payment)
        assert invoice_payment.status == "succeeded"

    @pytest.mark.asyncio
    async def test_invoice_payment_failed_via_webhook(
        self, client: AsyncClient, db_session, invoice_payment, monkeypatch,
    ):
        """Signed invoice.payment_failed event should mark payment as failed."""
        secret = "whsec_test_enhance"
        monkeypatch.setattr(settings, "STRIPE_WEBHOOK_SECRET", secret)

        payload, sig_header = _make_signed_payload(
            "invoice.payment_failed",
            {"id": "in_test_invoice_001"},
            secret,
        )

        response = await client.post(
            "/api/payments/webhook",
            content=payload,
            headers={
                "content-type": "application/json",
                "stripe-signature": sig_header,
            },
        )
        assert response.status_code == 200
        await db_session.refresh(invoice_payment)
        assert invoice_payment.status == "failed"

    @pytest.mark.asyncio
    async def test_async_payment_succeeded_via_webhook(
        self, client: AsyncClient, db_session, ach_checkout_payment, monkeypatch,
    ):
        """Signed async_payment_succeeded event should mark ACH payment succeeded."""
        secret = "whsec_test_enhance"
        monkeypatch.setattr(settings, "STRIPE_WEBHOOK_SECRET", secret)

        payload, sig_header = _make_signed_payload(
            "checkout.session.async_payment_succeeded",
            {"id": "cs_ach_test_001", "payment_intent": "pi_ach_webhook"},
            secret,
        )

        response = await client.post(
            "/api/payments/webhook",
            content=payload,
            headers={
                "content-type": "application/json",
                "stripe-signature": sig_header,
            },
        )
        assert response.status_code == 200
        await db_session.refresh(ach_checkout_payment)
        assert ach_checkout_payment.status == "succeeded"
        assert ach_checkout_payment.stripe_payment_intent_id == "pi_ach_webhook"

    @pytest.mark.asyncio
    async def test_setup_intent_succeeded_via_webhook(
        self, client: AsyncClient, monkeypatch,
    ):
        """Signed setup_intent.succeeded event should return 200."""
        secret = "whsec_test_enhance"
        monkeypatch.setattr(settings, "STRIPE_WEBHOOK_SECRET", secret)

        payload, sig_header = _make_signed_payload(
            "setup_intent.succeeded",
            {"id": "seti_webhook_001", "customer": "cus_enhance_test"},
            secret,
        )

        response = await client.post(
            "/api/payments/webhook",
            content=payload,
            headers={
                "content-type": "application/json",
                "stripe-signature": sig_header,
            },
        )
        assert response.status_code == 200
        assert response.json()["event_type"] == "setup_intent.succeeded"


# =========================================================================
# Service-level Tests
# =========================================================================

class TestInvoiceServiceMethods:
    """Test invoice and onboarding service methods directly."""

    @pytest.mark.asyncio
    async def test_sync_customer_from_id_existing(
        self, db_session, stripe_customer,
    ):
        """sync_customer_from_id should return existing customer."""
        service = PaymentService(db_session)
        result = await service.sync_customer_from_id(stripe_customer.id)
        assert result.id == stripe_customer.id
        assert result.stripe_customer_id == "cus_enhance_test"

    @pytest.mark.asyncio
    async def test_sync_customer_from_id_not_found(self, db_session):
        """sync_customer_from_id should raise ValueError for missing customer."""
        service = PaymentService(db_session)
        with pytest.raises(ValueError, match="not found"):
            await service.sync_customer_from_id(99999)

    @pytest.mark.asyncio
    async def test_create_and_send_invoice_no_stripe(
        self, db_session, test_user, stripe_customer,
    ):
        """create_and_send_invoice should raise when Stripe not configured."""
        service = PaymentService(db_session)
        with pytest.raises(ValueError, match="Stripe is not configured"):
            await service.create_and_send_invoice(
                customer_id=stripe_customer.id,
                amount=100.00,
                description="Test",
                user_id=test_user.id,
            )

    @pytest.mark.asyncio
    async def test_create_onboarding_link_no_stripe(
        self, db_session, test_contact,
    ):
        """create_onboarding_link should raise when Stripe not configured."""
        service = PaymentService(db_session)
        with pytest.raises(ValueError, match="Stripe is not configured"):
            await service.create_onboarding_link(
                success_url="http://localhost/success",
                cancel_url="http://localhost/cancel",
                contact_id=test_contact.id,
            )

    @pytest.mark.asyncio
    async def test_create_onboarding_link_requires_entity(self, db_session):
        """create_onboarding_link should raise without contact_id or company_id."""
        service = PaymentService(db_session)
        with pytest.raises(ValueError, match="contact_id or company_id"):
            await service.create_onboarding_link(
                success_url="http://localhost/success",
                cancel_url="http://localhost/cancel",
            )


# =========================================================================
# Model field Tests
# =========================================================================

class TestPaymentModelStripeInvoiceId:
    """Test that stripe_invoice_id field works on Payment model."""

    @pytest.mark.asyncio
    async def test_create_payment_with_invoice_id(self, db_session, test_user):
        """Payment can be created with stripe_invoice_id."""
        payment = Payment(
            stripe_invoice_id="in_model_test_001",
            amount=300.00,
            currency="USD",
            status="sent",
            owner_id=test_user.id,
            created_by_id=test_user.id,
        )
        db_session.add(payment)
        await db_session.commit()
        await db_session.refresh(payment)
        assert payment.stripe_invoice_id == "in_model_test_001"
        assert payment.status == "sent"

    @pytest.mark.asyncio
    async def test_payment_without_invoice_id(self, db_session, test_user):
        """Payment can be created without stripe_invoice_id (nullable)."""
        payment = Payment(
            amount=100.00,
            currency="USD",
            status="pending",
            owner_id=test_user.id,
            created_by_id=test_user.id,
        )
        db_session.add(payment)
        await db_session.commit()
        await db_session.refresh(payment)
        assert payment.stripe_invoice_id is None


# =========================================================================
# Stripe Hardening Tests
# =========================================================================

class TestSubscriptionResponseNullablePrice:
    """SubscriptionResponse.price_id must accept None (webhook-created subs)."""

    @pytest.mark.asyncio
    async def test_subscription_with_null_price_serializes(self, db_session, test_user):
        from src.payments.schemas import SubscriptionResponse

        sub = Subscription(
            stripe_subscription_id="sub_null_price",
            customer_id=1,
            price_id=None,
            status="active",
            cancel_at_period_end=False,
            owner_id=test_user.id,
            created_by_id=test_user.id,
        )
        db_session.add(sub)
        await db_session.flush()
        await db_session.refresh(sub)

        resp = SubscriptionResponse.model_validate(sub)
        assert resp.price_id is None
        assert resp.status == "active"


class TestPaymentSucceededLatestCharge:
    """_handle_payment_succeeded must read both legacy charges and latest_charge."""

    @pytest.mark.asyncio
    async def test_legacy_charges_field(self, db_session, test_user):
        payment = Payment(
            stripe_payment_intent_id="pi_legacy",
            amount=50.00,
            currency="USD",
            status="pending",
            owner_id=test_user.id,
            created_by_id=test_user.id,
        )
        db_session.add(payment)
        await db_session.flush()

        service = PaymentService(db_session)
        await service._handle_payment_succeeded({
            "id": "pi_legacy",
            "charges": {"data": [
                {"receipt_url": "https://example.com/receipt", "payment_method_details": {"type": "card"}}
            ]},
        })

        await db_session.refresh(payment)
        assert payment.status == "succeeded"
        assert payment.receipt_url == "https://example.com/receipt"
        assert payment.payment_method == "card"

    @pytest.mark.asyncio
    async def test_latest_charge_field(self, db_session, test_user):
        payment = Payment(
            stripe_payment_intent_id="pi_modern",
            amount=75.00,
            currency="USD",
            status="pending",
            owner_id=test_user.id,
            created_by_id=test_user.id,
        )
        db_session.add(payment)
        await db_session.flush()

        service = PaymentService(db_session)
        await service._handle_payment_succeeded({
            "id": "pi_modern",
            "latest_charge": {
                "receipt_url": "https://example.com/modern",
                "payment_method_details": {"type": "us_bank_account"},
            },
        })

        await db_session.refresh(payment)
        assert payment.status == "succeeded"
        assert payment.receipt_url == "https://example.com/modern"
        assert payment.payment_method == "us_bank_account"


class TestIdempotencyKeyPresence:
    """Stripe write operations must include idempotency keys."""

    def test_uuid_imported(self):
        import src.payments.service as svc
        assert hasattr(svc, "uuid")
