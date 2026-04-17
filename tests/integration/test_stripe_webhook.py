"""Integration tests for POST /api/payments/webhook (Stripe signed events)."""

import hashlib
import hmac
import json
import time
from unittest.mock import patch

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.models import User
from src.payments.models import Payment, StripeCustomer, Subscription
from src.webhooks.stripe_events import WebhookEvent

WEBHOOK_SECRET = "whsec_test_secret_for_tests_only"
ENDPOINT = "/api/payments/webhook"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sign(payload: dict, secret: str = WEBHOOK_SECRET) -> dict:
    """Build Stripe-style HMAC-SHA256 signature headers."""
    body = json.dumps(payload, separators=(",", ":"))
    ts = int(time.time())
    sig = hmac.new(secret.encode(), f"{ts}.{body}".encode(), hashlib.sha256).hexdigest()
    return {
        "Stripe-Signature": f"t={ts},v1={sig}",
        "Content-Type": "application/json",
    }


def _event(event_type: str, obj: dict, event_id: str | None = None) -> dict:
    """Minimal Stripe event envelope."""
    return {
        "id": event_id or f"evt_test_{event_type.replace('.', '_')}",
        "type": event_type,
        "data": {"object": obj},
    }


def _post(client: AsyncClient, payload: dict, secret: str = WEBHOOK_SECRET):
    """POST a signed webhook payload."""
    body = json.dumps(payload, separators=(",", ":")).encode()
    headers = _sign(payload, secret)
    return client.post(ENDPOINT, content=body, headers=headers)


# ---------------------------------------------------------------------------
# Fixture: patch settings so STRIPE_WEBHOOK_SECRET is set and STRIPE_SECRET_KEY
# is empty — forces the hand-rolled HMAC path (no stripe SDK calls needed)
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _patch_settings():
    """Inject webhook secret into settings; keep STRIPE_SECRET_KEY blank."""
    class _FakeSettings:
        STRIPE_WEBHOOK_SECRET = WEBHOOK_SECRET
        STRIPE_SECRET_KEY = ""  # forces _get_stripe() → None

    with patch("src.payments.service.settings", _FakeSettings()):
        yield


# ---------------------------------------------------------------------------
# Fixtures: minimal DB objects
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture()
async def stripe_customer(db_session: AsyncSession, test_user: User) -> StripeCustomer:
    """A StripeCustomer row with no linked contact/company (sufficient for webhook tests)."""
    sc = StripeCustomer(
        stripe_customer_id="cus_test_webhook",
        email="webhook@example.com",
        name="Webhook Customer",
    )
    db_session.add(sc)
    await db_session.flush()
    await db_session.refresh(sc)
    return sc


@pytest_asyncio.fixture()
async def subscription(db_session: AsyncSession, stripe_customer: StripeCustomer, test_user: User) -> Subscription:
    """An existing Subscription row."""
    sub = Subscription(
        stripe_subscription_id="sub_existing",
        customer_id=stripe_customer.id,
        status="active",
        owner_id=test_user.id,
        created_by_id=test_user.id,
    )
    db_session.add(sub)
    await db_session.flush()
    await db_session.refresh(sub)
    return sub


@pytest_asyncio.fixture()
async def pending_payment(db_session: AsyncSession, test_user: User) -> Payment:
    """A Payment row in 'pending' status with a known invoice ID."""
    p = Payment(
        stripe_invoice_id="in_test_pending",
        amount=99.00,
        currency="USD",
        status="pending",
        owner_id=test_user.id,
        created_by_id=test_user.id,
    )
    db_session.add(p)
    await db_session.flush()
    await db_session.refresh(p)
    return p


# ---------------------------------------------------------------------------
# Signature verification
# ---------------------------------------------------------------------------

class TestSignatureVerification:
    async def test_missing_signature_returns_400(self, client: AsyncClient):
        """No Stripe-Signature header → 400."""
        resp = await client.post(
            ENDPOINT,
            content=b'{"id":"evt_1","type":"ping","data":{"object":{}}}',
            headers={"Content-Type": "application/json"},
        )
        assert resp.status_code == 400

    async def test_wrong_signature_returns_400(self, client: AsyncClient):
        """Correct format but wrong secret → 400."""
        payload = _event("ping", {})
        body = json.dumps(payload, separators=(",", ":")).encode()
        bad_headers = _sign(payload, secret="wrong_secret")
        resp = await client.post(ENDPOINT, content=body, headers=bad_headers)
        assert resp.status_code == 400

    async def test_malformed_body_returns_400(self, client: AsyncClient):
        """Non-JSON body with a valid-looking sig header → 400 (JSON parse fails)."""
        ts = int(time.time())
        body = b"not-json-at-all"
        sig = hmac.new(
            WEBHOOK_SECRET.encode(), f"{ts}.".encode() + body, hashlib.sha256
        ).hexdigest()
        resp = await client.post(
            ENDPOINT,
            content=body,
            headers={"Stripe-Signature": f"t={ts},v1={sig}", "Content-Type": "application/json"},
        )
        assert resp.status_code == 400

    async def test_valid_signature_unknown_type_returns_200(self, client: AsyncClient):
        """Unknown event type with valid sig → 200, no-op (Stripe always expects 2xx)."""
        payload = _event("totally.unknown.event_type", {"foo": "bar"})
        resp = await _post(client, payload)
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Idempotency
# ---------------------------------------------------------------------------

class TestIdempotency:
    async def test_replay_same_event_id_is_safe(self, client: AsyncClient, db_session: AsyncSession):
        """Replaying the same event_id returns 200 with replayed:True, no duplicate DB rows."""
        payload = _event("customer.subscription.deleted", {"id": "sub_gone"}, event_id="evt_dedup_001")

        resp1 = await _post(client, payload)
        assert resp1.status_code == 200

        resp2 = await _post(client, payload)
        assert resp2.status_code == 200
        assert resp2.json().get("status") == "replayed"

        rows = await db_session.execute(
            select(WebhookEvent).where(WebhookEvent.event_id == "evt_dedup_001")
        )
        assert len(rows.scalars().all()) == 1


# ---------------------------------------------------------------------------
# Event type: customer.subscription.created
# ---------------------------------------------------------------------------

class TestSubscriptionCreated:
    async def test_creates_subscription_row(
        self, client: AsyncClient, db_session: AsyncSession, stripe_customer: StripeCustomer
    ):
        """subscription.created inserts a local Subscription row."""
        obj = {
            "id": "sub_new_001",
            "customer": stripe_customer.stripe_customer_id,
            "status": "active",
            "current_period_start": int(time.time()),
            "current_period_end": int(time.time()) + 2592000,
            "cancel_at_period_end": False,
            "items": {"data": []},
        }
        resp = await _post(client, _event("customer.subscription.created", obj))
        assert resp.status_code == 200

        result = await db_session.execute(
            select(Subscription).where(Subscription.stripe_subscription_id == "sub_new_001")
        )
        sub = result.scalar_one_or_none()
        assert sub is not None
        assert sub.status == "active"

    async def test_unknown_customer_does_not_crash(self, client: AsyncClient):
        """subscription.created for an unknown Stripe customer → 200, no insert."""
        obj = {
            "id": "sub_orphan",
            "customer": "cus_does_not_exist",
            "status": "active",
            "current_period_start": int(time.time()),
            "current_period_end": int(time.time()) + 2592000,
            "cancel_at_period_end": False,
            "items": {"data": []},
        }
        resp = await _post(client, _event("customer.subscription.created", obj))
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Event type: customer.subscription.updated
# ---------------------------------------------------------------------------

class TestSubscriptionUpdated:
    async def test_updates_period_dates(
        self, client: AsyncClient, db_session: AsyncSession, subscription: Subscription
    ):
        """subscription.updated refreshes period timestamps (regression: PR #43)."""
        new_end_ts = int(time.time()) + 5184000  # +60 days
        obj = {
            "id": subscription.stripe_subscription_id,
            "status": "active",
            "current_period_start": int(time.time()),
            "current_period_end": new_end_ts,
            "cancel_at_period_end": False,
        }
        resp = await _post(client, _event("customer.subscription.updated", obj))
        assert resp.status_code == 200

        await db_session.refresh(subscription)
        # Verify the field was updated: it must be set and further in the future
        # than the current time (SQLite strips tz so we compare naive timestamps)
        assert subscription.current_period_end is not None
        now_dt = subscription.current_period_end.replace(tzinfo=None)
        import datetime as _dt
        assert now_dt > _dt.datetime.utcnow() + _dt.timedelta(days=55)

    async def test_sets_cancel_at_period_end(
        self, client: AsyncClient, db_session: AsyncSession, subscription: Subscription
    ):
        """subscription.updated can flip cancel_at_period_end."""
        obj = {
            "id": subscription.stripe_subscription_id,
            "status": "active",
            "cancel_at_period_end": True,
        }
        resp = await _post(client, _event("customer.subscription.updated", obj))
        assert resp.status_code == 200

        await db_session.refresh(subscription)
        assert subscription.cancel_at_period_end is True


# ---------------------------------------------------------------------------
# Event type: customer.subscription.deleted
# ---------------------------------------------------------------------------

class TestSubscriptionDeleted:
    async def test_marks_subscription_canceled(
        self, client: AsyncClient, db_session: AsyncSession, subscription: Subscription
    ):
        """subscription.deleted sets status to 'canceled'."""
        obj = {"id": subscription.stripe_subscription_id}
        resp = await _post(client, _event("customer.subscription.deleted", obj))
        assert resp.status_code == 200

        await db_session.refresh(subscription)
        assert subscription.status == "canceled"


# ---------------------------------------------------------------------------
# Event type: invoice.paid
# ---------------------------------------------------------------------------

class TestInvoicePaid:
    async def test_marks_existing_payment_succeeded(
        self, client: AsyncClient, db_session: AsyncSession, pending_payment: Payment
    ):
        """invoice.paid marks an existing Payment row as succeeded."""
        obj = {"id": pending_payment.stripe_invoice_id, "amount_paid": 9900, "currency": "usd"}
        resp = await _post(client, _event("invoice.paid", obj))
        assert resp.status_code == 200

        await db_session.refresh(pending_payment)
        assert pending_payment.status == "succeeded"

    async def test_renewal_invoice_creates_payment_row(
        self, client: AsyncClient, db_session: AsyncSession,
        subscription: Subscription, stripe_customer: StripeCustomer,
    ):
        """invoice.paid for an unknown invoice with a known subscription → new Payment row."""
        obj = {
            "id": "in_renewal_001",
            "subscription": subscription.stripe_subscription_id,
            "customer": stripe_customer.stripe_customer_id,
            "amount_paid": 4900,
            "currency": "usd",
        }
        resp = await _post(client, _event("invoice.paid", obj))
        assert resp.status_code == 200

        result = await db_session.execute(
            select(Payment).where(Payment.stripe_invoice_id == "in_renewal_001")
        )
        payment = result.scalar_one_or_none()
        assert payment is not None
        assert payment.status == "succeeded"


# ---------------------------------------------------------------------------
# Event type: invoice.payment_failed
# ---------------------------------------------------------------------------

class TestInvoicePaymentFailed:
    async def test_marks_payment_failed(
        self, client: AsyncClient, db_session: AsyncSession, pending_payment: Payment
    ):
        """invoice.payment_failed sets Payment status to 'failed'."""
        obj = {"id": pending_payment.stripe_invoice_id}
        resp = await _post(client, _event("invoice.payment_failed", obj))
        assert resp.status_code == 200

        await db_session.refresh(pending_payment)
        assert pending_payment.status == "failed"

    async def test_does_not_overwrite_succeeded(
        self, client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        """invoice.payment_failed won't downgrade an already-succeeded payment."""
        p = Payment(
            stripe_invoice_id="in_already_succeeded",
            amount=50.00,
            currency="USD",
            status="succeeded",
            owner_id=test_user.id,
            created_by_id=test_user.id,
        )
        db_session.add(p)
        await db_session.flush()

        obj = {"id": "in_already_succeeded"}
        resp = await _post(client, _event("invoice.payment_failed", obj))
        assert resp.status_code == 200

        await db_session.refresh(p)
        assert p.status == "succeeded"
