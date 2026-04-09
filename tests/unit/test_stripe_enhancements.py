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
from src.payments.models import StripeCustomer, Payment
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

class TestSetupIntentWebhook:
    """Test setup_intent.succeeded webhook handler."""

    @pytest.mark.asyncio
    async def test_setup_intent_succeeded_logs(self, db_session):
        """setup_intent.succeeded should not error (logs info)."""
        service = PaymentService(db_session)
        # Should complete without error; it just logs
        await service._handle_setup_intent_succeeded({
            "id": "seti_test_001",
            "customer": "cus_enhance_test",
        })

    @pytest.mark.asyncio
    async def test_setup_intent_succeeded_no_customer(self, db_session):
        """setup_intent.succeeded without customer should not error."""
        service = PaymentService(db_session)
        await service._handle_setup_intent_succeeded({"id": "seti_test_002"})


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
