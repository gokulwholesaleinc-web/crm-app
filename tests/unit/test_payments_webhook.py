"""Stripe webhook handler tests for PaymentService.

Covers:
1. _verify_webhook_signature — valid, invalid, stale timestamp
2. process_webhook idempotency — duplicate event_id not reprocessed
3. _handle_invoice_paid — existing Payment update + subscription-renewal insert
4. _handle_invoice_payment_failed — sets status to 'failed'
5. _handle_subscription_created — creates local Subscription row
6. _handle_subscription_updated — updates status on cancel/pause/reactivate
7. _to_cents — ROUND_HALF_UP on $19.995 → 2000¢
"""

import hashlib
import hmac
import json
import time
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.models import User
from src.payments.models import Payment, StripeCustomer, Subscription
from src.payments.service import PaymentService, _to_cents
from src.webhooks.stripe_events import WebhookEvent


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

WEBHOOK_SECRET = "whsec_test_secret"


def _make_sig_header(payload: bytes, secret: str, ts: int | None = None) -> str:
    if ts is None:
        ts = int(time.time())
    signed = f"{ts}.".encode() + payload
    sig = hmac.new(secret.encode(), signed, hashlib.sha256).hexdigest()
    return f"t={ts},v1={sig}"


def _make_event(event_type: str, obj: dict, event_id: str = "evt_test_001") -> dict:
    return {
        "id": event_id,
        "type": event_type,
        "data": {"object": obj},
    }


def _encode(event: dict) -> bytes:
    return json.dumps(event).encode()


# ---------------------------------------------------------------------------
# Target 7: _to_cents — ROUND_HALF_UP
# ---------------------------------------------------------------------------


class TestToCents:
    """_to_cents rounds half-up, not half-even."""

    def test_round_half_up_19_995(self):
        """$19.995 must round to 2000¢ (not 1999¢ from truncation)."""
        assert _to_cents("19.995") == 2000

    def test_integer_input(self):
        assert _to_cents(10) == 1000

    def test_float_input(self):
        assert _to_cents(9.99) == 999

    def test_decimal_input(self):
        assert _to_cents(Decimal("1.005")) == 101

    def test_zero(self):
        assert _to_cents(0) == 0

    def test_large_amount(self):
        assert _to_cents("9999.99") == 999999


# ---------------------------------------------------------------------------
# Target 1: _verify_webhook_signature
# ---------------------------------------------------------------------------


class TestVerifyWebhookSignature:
    """_verify_webhook_signature validates Stripe HMAC-SHA256 headers."""

    def test_valid_signature_returns_true(self):
        """Fresh, correctly-signed payload returns True."""
        payload = b'{"id":"evt_1","type":"test"}'
        sig = _make_sig_header(payload, WEBHOOK_SECRET)
        assert PaymentService._verify_webhook_signature(payload, sig, WEBHOOK_SECRET)

    def test_wrong_secret_returns_false(self):
        """Payload signed with different secret must be rejected."""
        payload = b'{"id":"evt_1","type":"test"}'
        sig = _make_sig_header(payload, "wrong_secret")
        assert not PaymentService._verify_webhook_signature(payload, sig, WEBHOOK_SECRET)

    def test_tampered_payload_returns_false(self):
        """Signature generated for original payload doesn't match tampered payload."""
        payload = b'{"id":"evt_1","type":"test"}'
        sig = _make_sig_header(payload, WEBHOOK_SECRET)
        tampered = b'{"id":"evt_1","type":"EVIL"}'
        assert not PaymentService._verify_webhook_signature(tampered, sig, WEBHOOK_SECRET)

    def test_stale_timestamp_returns_false(self):
        """Payload with timestamp older than tolerance (300s) is rejected."""
        payload = b'{"id":"evt_1","type":"test"}'
        old_ts = int(time.time()) - 400
        sig = _make_sig_header(payload, WEBHOOK_SECRET, ts=old_ts)
        assert not PaymentService._verify_webhook_signature(payload, sig, WEBHOOK_SECRET)

    def test_missing_v1_field_returns_false(self):
        """Header without v1 field returns False."""
        payload = b'{"id":"evt_1"}'
        assert not PaymentService._verify_webhook_signature(
            payload, f"t={int(time.time())}", WEBHOOK_SECRET
        )

    def test_empty_header_returns_false(self):
        assert not PaymentService._verify_webhook_signature(b"payload", "", WEBHOOK_SECRET)


# ---------------------------------------------------------------------------
# Base fixture: PaymentService backed by real SQLite session
# ---------------------------------------------------------------------------


@pytest.fixture
def payment_service(db_session: AsyncSession) -> PaymentService:
    svc = PaymentService(db_session)
    return svc


@pytest.fixture
def patched_settings(monkeypatch):
    """Patch settings so process_webhook uses the hand-rolled fallback path."""
    with patch("src.payments.service._get_stripe", return_value=None):
        with patch("src.payments.service.settings") as mock_settings:
            mock_settings.STRIPE_WEBHOOK_SECRET = WEBHOOK_SECRET
            mock_settings.STRIPE_SECRET_KEY = ""
            yield mock_settings


# ---------------------------------------------------------------------------
# Target 1 (continued): idempotency via process_webhook
# ---------------------------------------------------------------------------


class TestProcessWebhookIdempotency:
    """Replayed signed payloads must not re-run handlers."""

    @pytest.mark.asyncio
    async def test_duplicate_event_id_returns_replayed(
        self,
        db_session: AsyncSession,
        payment_service: PaymentService,
        patched_settings,
        test_user: User,
    ):
        """Second delivery of same event_id returns status='replayed', no duplicate row."""
        event = _make_event(
            "payment_intent.payment_failed",
            {"id": "pi_idem_test"},
            event_id="evt_idem_001",
        )
        payload = _encode(event)
        sig = _make_sig_header(payload, WEBHOOK_SECRET)

        # First call — processed
        r1 = await payment_service.process_webhook(payload, sig)
        assert r1["status"] == "processed"
        assert r1["event_id"] == "evt_idem_001"

        # Rebuild sig with fresh timestamp (Stripe always uses current time)
        sig2 = _make_sig_header(payload, WEBHOOK_SECRET)
        r2 = await payment_service.process_webhook(payload, sig2)
        assert r2["status"] == "replayed"

        # Only one WebhookEvent row should exist
        result = await db_session.execute(
            select(WebhookEvent).where(WebhookEvent.event_id == "evt_idem_001")
        )
        rows = result.scalars().all()
        assert len(rows) == 1

    @pytest.mark.asyncio
    async def test_invalid_signature_raises_value_error(
        self,
        payment_service: PaymentService,
        patched_settings,
    ):
        """Tampered payload raises ValueError (400 in the router)."""
        event = _make_event("invoice.paid", {"id": "in_x"})
        payload = _encode(event)
        bad_sig = _make_sig_header(payload, "bad_secret")

        with pytest.raises(ValueError, match="Invalid webhook"):
            await payment_service.process_webhook(payload, bad_sig)


# ---------------------------------------------------------------------------
# Target 3: _handle_invoice_paid
# ---------------------------------------------------------------------------


class TestHandleInvoicePaid:
    """invoice.paid — marks existing payment succeeded OR inserts renewal row."""

    @pytest.mark.asyncio
    async def test_existing_payment_marked_succeeded(
        self,
        db_session: AsyncSession,
        payment_service: PaymentService,
        test_user: User,
    ):
        """When a Payment row with stripe_invoice_id exists, it becomes succeeded."""
        payment = Payment(
            stripe_invoice_id="in_existing_001",
            amount=100.00,
            currency="USD",
            status="pending",
            owner_id=test_user.id,
            created_by_id=test_user.id,
        )
        db_session.add(payment)
        await db_session.commit()
        await db_session.refresh(payment)

        await payment_service._handle_invoice_paid(
            {"id": "in_existing_001", "amount_paid": 10000, "currency": "usd"}
        )
        await db_session.refresh(payment)
        assert payment.status == "succeeded"

    @pytest.mark.asyncio
    async def test_already_succeeded_not_modified(
        self,
        db_session: AsyncSession,
        payment_service: PaymentService,
        test_user: User,
    ):
        """If existing Payment is already succeeded, handler is a no-op (no flush side-effects)."""
        payment = Payment(
            stripe_invoice_id="in_existing_002",
            amount=50.00,
            currency="USD",
            status="succeeded",
            owner_id=test_user.id,
            created_by_id=test_user.id,
        )
        db_session.add(payment)
        await db_session.commit()
        await db_session.refresh(payment)

        await payment_service._handle_invoice_paid(
            {"id": "in_existing_002", "amount_paid": 5000, "currency": "usd"}
        )
        await db_session.refresh(payment)
        assert payment.status == "succeeded"

    @pytest.mark.asyncio
    async def test_subscription_renewal_inserts_new_payment(
        self,
        db_session: AsyncSession,
        payment_service: PaymentService,
        test_user: User,
    ):
        """New invoice for known customer → inserts a fresh succeeded Payment row."""
        customer = StripeCustomer(
            stripe_customer_id="cus_renewal_01",
            email="renewal@example.com",
            name="Renewal Customer",
        )
        db_session.add(customer)
        await db_session.flush()

        sub = Subscription(
            stripe_subscription_id="sub_renewal_01",
            customer_id=customer.id,
            status="active",
            owner_id=test_user.id,
            created_by_id=test_user.id,
        )
        db_session.add(sub)
        await db_session.commit()

        await payment_service._handle_invoice_paid({
            "id": "in_renewal_01",
            "subscription": "sub_renewal_01",
            "customer": "cus_renewal_01",
            "amount_paid": 2999,
            "currency": "usd",
        })

        result = await db_session.execute(
            select(Payment).where(Payment.stripe_invoice_id == "in_renewal_01")
        )
        new_payment = result.scalar_one_or_none()
        assert new_payment is not None
        assert new_payment.status == "succeeded"
        assert new_payment.customer_id == customer.id
        assert new_payment.amount == Decimal("29.99")

    @pytest.mark.asyncio
    async def test_unknown_customer_and_subscription_drops_silently(
        self,
        db_session: AsyncSession,
        payment_service: PaymentService,
    ):
        """No subscription or customer match → no Payment row inserted, no exception."""
        await payment_service._handle_invoice_paid({
            "id": "in_orphan_01",
            "subscription": "sub_nobody",
            "customer": "cus_nobody",
            "amount_paid": 500,
            "currency": "usd",
        })

        result = await db_session.execute(
            select(Payment).where(Payment.stripe_invoice_id == "in_orphan_01")
        )
        assert result.scalar_one_or_none() is None

    @pytest.mark.asyncio
    async def test_customer_match_without_subscription_inserts_payment(
        self,
        db_session: AsyncSession,
        payment_service: PaymentService,
        test_user: User,
    ):
        """Customer known but no subscription → still inserts Payment (customer-match path)."""
        customer = StripeCustomer(
            stripe_customer_id="cus_nosubscription_01",
            email="nosub@example.com",
            name="No Sub Customer",
        )
        db_session.add(customer)
        await db_session.commit()

        await payment_service._handle_invoice_paid({
            "id": "in_nosub_01",
            "subscription": None,
            "customer": "cus_nosubscription_01",
            "amount_paid": 1500,
            "currency": "usd",
        })

        result = await db_session.execute(
            select(Payment).where(Payment.stripe_invoice_id == "in_nosub_01")
        )
        new_payment = result.scalar_one_or_none()
        assert new_payment is not None
        assert new_payment.status == "succeeded"
        assert new_payment.customer_id == customer.id


# ---------------------------------------------------------------------------
# Target 4: _handle_invoice_payment_failed
# ---------------------------------------------------------------------------


class TestHandleInvoicePaymentFailed:
    """invoice.payment_failed sets payment status to 'failed'."""

    @pytest.mark.asyncio
    async def test_pending_payment_set_to_failed(
        self,
        db_session: AsyncSession,
        payment_service: PaymentService,
        test_user: User,
    ):
        payment = Payment(
            stripe_invoice_id="in_fail_001",
            amount=75.00,
            currency="USD",
            status="pending",
            owner_id=test_user.id,
            created_by_id=test_user.id,
        )
        db_session.add(payment)
        await db_session.commit()
        await db_session.refresh(payment)

        await payment_service._handle_invoice_payment_failed({"id": "in_fail_001"})
        await db_session.refresh(payment)
        assert payment.status == "failed"

    @pytest.mark.asyncio
    async def test_succeeded_payment_not_modified(
        self,
        db_session: AsyncSession,
        payment_service: PaymentService,
        test_user: User,
    ):
        """Guard: already-succeeded payment must not be moved to failed."""
        payment = Payment(
            stripe_invoice_id="in_fail_002",
            amount=50.00,
            currency="USD",
            status="succeeded",
            owner_id=test_user.id,
            created_by_id=test_user.id,
        )
        db_session.add(payment)
        await db_session.commit()
        await db_session.refresh(payment)

        await payment_service._handle_invoice_payment_failed({"id": "in_fail_002"})
        await db_session.refresh(payment)
        assert payment.status == "succeeded"

    @pytest.mark.asyncio
    async def test_unknown_invoice_is_noop(
        self,
        db_session: AsyncSession,
        payment_service: PaymentService,
    ):
        """Missing invoice_id in DB → silent no-op, no exception."""
        await payment_service._handle_invoice_payment_failed({"id": "in_nobody"})


# ---------------------------------------------------------------------------
# Target 5: _handle_subscription_created
# ---------------------------------------------------------------------------


class TestHandleSubscriptionCreated:
    """customer.subscription.created inserts a local Subscription row."""

    @pytest.mark.asyncio
    async def test_creates_subscription_row(
        self,
        db_session: AsyncSession,
        payment_service: PaymentService,
        test_user: User,
    ):
        customer = StripeCustomer(
            stripe_customer_id="cus_subcreate_01",
            email="subcreate@example.com",
            name="Sub Create Customer",
        )
        db_session.add(customer)
        await db_session.commit()

        ts_now = int(time.time())
        await payment_service._handle_subscription_created({
            "id": "sub_create_01",
            "customer": "cus_subcreate_01",
            "status": "active",
            "cancel_at_period_end": False,
            "current_period_start": ts_now,
            "current_period_end": ts_now + 2592000,
            "items": {"data": []},
        })

        result = await db_session.execute(
            select(Subscription).where(
                Subscription.stripe_subscription_id == "sub_create_01"
            )
        )
        sub = result.scalar_one_or_none()
        assert sub is not None
        assert sub.status == "active"
        assert sub.customer_id == customer.id

    @pytest.mark.asyncio
    async def test_unknown_customer_skips_insert(
        self,
        db_session: AsyncSession,
        payment_service: PaymentService,
    ):
        """No matching StripeCustomer → handler logs warning and returns without inserting."""
        await payment_service._handle_subscription_created({
            "id": "sub_orphan_01",
            "customer": "cus_nobody",
            "status": "active",
            "cancel_at_period_end": False,
            "items": {"data": []},
        })

        result = await db_session.execute(
            select(Subscription).where(
                Subscription.stripe_subscription_id == "sub_orphan_01"
            )
        )
        assert result.scalar_one_or_none() is None

    @pytest.mark.asyncio
    async def test_duplicate_subscription_delegates_to_updated(
        self,
        db_session: AsyncSession,
        payment_service: PaymentService,
        test_user: User,
    ):
        """subscription.created for already-known sub falls through to update handler."""
        customer = StripeCustomer(
            stripe_customer_id="cus_subdedup_01",
            email="subdedup@example.com",
            name="Sub Dedup Customer",
        )
        db_session.add(customer)
        await db_session.flush()

        existing_sub = Subscription(
            stripe_subscription_id="sub_dedup_01",
            customer_id=customer.id,
            status="active",
            owner_id=test_user.id,
            created_by_id=test_user.id,
        )
        db_session.add(existing_sub)
        await db_session.commit()

        # Fire created again — should behave like an update
        await payment_service._handle_subscription_created({
            "id": "sub_dedup_01",
            "customer": "cus_subdedup_01",
            "status": "past_due",
            "cancel_at_period_end": False,
            "items": {"data": []},
        })

        await db_session.refresh(existing_sub)
        assert existing_sub.status == "past_due"


# ---------------------------------------------------------------------------
# Target 6: _handle_subscription_updated
# ---------------------------------------------------------------------------


class TestHandleSubscriptionUpdated:
    """customer.subscription.updated refreshes status and cancel_at_period_end."""

    @pytest.mark.asyncio
    async def test_cancel_at_period_end_update(
        self,
        db_session: AsyncSession,
        payment_service: PaymentService,
        test_user: User,
    ):
        customer = StripeCustomer(
            stripe_customer_id="cus_subupdate_01",
            email="subupdate@example.com",
            name="Sub Update Customer",
        )
        db_session.add(customer)
        await db_session.flush()

        sub = Subscription(
            stripe_subscription_id="sub_update_01",
            customer_id=customer.id,
            status="active",
            cancel_at_period_end=False,
            owner_id=test_user.id,
            created_by_id=test_user.id,
        )
        db_session.add(sub)
        await db_session.commit()

        await payment_service._handle_subscription_updated({
            "id": "sub_update_01",
            "status": "active",
            "cancel_at_period_end": True,
        })

        await db_session.refresh(sub)
        assert sub.cancel_at_period_end is True

    @pytest.mark.asyncio
    async def test_pause_status_update(
        self,
        db_session: AsyncSession,
        payment_service: PaymentService,
        test_user: User,
    ):
        customer = StripeCustomer(
            stripe_customer_id="cus_subupdate_02",
            email="subupdate2@example.com",
            name="Sub Pause Customer",
        )
        db_session.add(customer)
        await db_session.flush()

        sub = Subscription(
            stripe_subscription_id="sub_update_02",
            customer_id=customer.id,
            status="active",
            owner_id=test_user.id,
            created_by_id=test_user.id,
        )
        db_session.add(sub)
        await db_session.commit()

        await payment_service._handle_subscription_updated({
            "id": "sub_update_02",
            "status": "paused",
            "cancel_at_period_end": False,
        })

        await db_session.refresh(sub)
        assert sub.status == "paused"

    @pytest.mark.asyncio
    async def test_reactivation_status_update(
        self,
        db_session: AsyncSession,
        payment_service: PaymentService,
        test_user: User,
    ):
        customer = StripeCustomer(
            stripe_customer_id="cus_subupdate_03",
            email="subupdate3@example.com",
            name="Sub Reactivate Customer",
        )
        db_session.add(customer)
        await db_session.flush()

        sub = Subscription(
            stripe_subscription_id="sub_update_03",
            customer_id=customer.id,
            status="past_due",
            owner_id=test_user.id,
            created_by_id=test_user.id,
        )
        db_session.add(sub)
        await db_session.commit()

        await payment_service._handle_subscription_updated({
            "id": "sub_update_03",
            "status": "active",
            "cancel_at_period_end": False,
        })

        await db_session.refresh(sub)
        assert sub.status == "active"

    @pytest.mark.asyncio
    async def test_unknown_subscription_is_noop(
        self,
        db_session: AsyncSession,
        payment_service: PaymentService,
    ):
        """No matching Subscription → silent no-op, no exception."""
        await payment_service._handle_subscription_updated({
            "id": "sub_nobody",
            "status": "canceled",
            "cancel_at_period_end": True,
        })
