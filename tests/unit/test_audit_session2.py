"""Regression tests for audit remediation Session 2.

Covers the behaviors added in Session 2 that don't have natural homes in
existing module-specific test files:

1. Stripe webhook replay dedup against the new `webhook_events` table.
2. Subscription renewal path on `invoice.paid` (new Payment row insert).
3. `customer.subscription.created` creating a local Subscription row.
4. Quote/Proposal public token lookup — sequential quote_number no
   longer works.
5. Signer-email validation on public quote accept.
6. Google OAuth state cookie CSRF defense.
7. `_to_cents` ROUND_HALF_UP on half-cent values.

No mocks. Stripe API calls are only exercised via the webhook path,
which we invoke directly — no real HTTP. Where tests need a signed
webhook payload they use the same HMAC helper the server does. Where
tests need to talk to the "stripe" library (webhook construct_event),
we set STRIPE_SECRET_KEY to empty so the router uses the internal
HMAC verifier, which is fully owned by us.
"""

import hashlib
import hmac
import json
import secrets
import time
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.models import User
from src.auth.security import create_access_token
from src.contacts.models import Contact
from src.payments.models import Payment, StripeCustomer, Subscription
from src.payments.service import PaymentService, _to_cents
from src.proposals.models import Proposal
from src.quotes.models import Quote, QuoteLineItem
from src.webhooks.stripe_events import WebhookEvent


def _auth_header(user: User) -> dict:
    token = create_access_token(data={"sub": str(user.id)})
    return {"Authorization": f"Bearer {token}"}


def _sign_webhook(payload: bytes, secret: str, timestamp: int | None = None) -> str:
    """Replicate Stripe's t=<ts>,v1=<hex> signature header format."""
    ts = timestamp if timestamp is not None else int(time.time())
    signed_payload = f"{ts}.".encode() + payload
    digest = hmac.new(secret.encode(), signed_payload, hashlib.sha256).hexdigest()
    return f"t={ts},v1={digest}"


# =============================================================================
# _to_cents ROUND_HALF_UP
# =============================================================================


class TestToCents:
    """_to_cents replaces int(Decimal(str(amount)) * 100) truncation."""

    def test_rounds_half_up(self):
        """19.995 rounds to 2000, not 1999."""
        assert _to_cents(19.995) == 2000

    def test_whole_dollar(self):
        assert _to_cents(100) == 10000

    def test_decimal_input(self):
        assert _to_cents(Decimal("12.34")) == 1234

    def test_string_input(self):
        assert _to_cents("0.10") == 10

    def test_rounds_half_up_exact_half(self):
        """$0.005 rounds up to 1 cent, not down."""
        assert _to_cents(Decimal("0.005")) == 1


# =============================================================================
# Webhook replay dedup
# =============================================================================


class TestWebhookReplayDedup:
    """Stripe webhook idempotency via the webhook_events table."""

    @pytest.mark.asyncio
    async def test_webhook_dedup_marks_replay(
        self, client: AsyncClient, db_session: AsyncSession, monkeypatch,
    ):
        """A duplicate event_id returns status=replayed and doesn't re-run handlers."""
        monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "test-whsec")
        from src.config import settings
        original_secret = settings.STRIPE_WEBHOOK_SECRET
        settings.STRIPE_WEBHOOK_SECRET = "test-whsec"
        try:
            event_id = f"evt_{secrets.token_hex(8)}"
            payload = json.dumps({
                "id": event_id,
                "type": "setup_intent.succeeded",
                "data": {"object": {"id": "seti_test", "customer": "cus_test"}},
            }).encode()
            sig = _sign_webhook(payload, "test-whsec")

            # First delivery — processed.
            r1 = await client.post(
                "/api/payments/webhook",
                content=payload,
                headers={"stripe-signature": sig, "content-type": "application/json"},
            )
            assert r1.status_code == 200, r1.text
            assert r1.json()["status"] == "processed"

            # Row recorded in webhook_events.
            result = await db_session.execute(
                select(WebhookEvent).where(WebhookEvent.event_id == event_id)
            )
            assert result.scalar_one() is not None

            # Second delivery — same event_id, same signature — replayed.
            r2 = await client.post(
                "/api/payments/webhook",
                content=payload,
                headers={"stripe-signature": sig, "content-type": "application/json"},
            )
            assert r2.status_code == 200
            assert r2.json()["status"] == "replayed"
        finally:
            settings.STRIPE_WEBHOOK_SECRET = original_secret

    @pytest.mark.asyncio
    async def test_webhook_rejects_stale_timestamp(
        self, client: AsyncClient, monkeypatch,
    ):
        """A payload more than the tolerance window old is rejected."""
        from src.config import settings
        original_secret = settings.STRIPE_WEBHOOK_SECRET
        settings.STRIPE_WEBHOOK_SECRET = "test-whsec"
        try:
            event_id = f"evt_{secrets.token_hex(8)}"
            payload = json.dumps({
                "id": event_id,
                "type": "setup_intent.succeeded",
                "data": {"object": {}},
            }).encode()
            # 10 minutes in the past — well beyond the 5-minute tolerance.
            stale_ts = int(time.time()) - 600
            sig = _sign_webhook(payload, "test-whsec", timestamp=stale_ts)

            resp = await client.post(
                "/api/payments/webhook",
                content=payload,
                headers={"stripe-signature": sig, "content-type": "application/json"},
            )
            assert resp.status_code == 400
        finally:
            settings.STRIPE_WEBHOOK_SECRET = original_secret


# =============================================================================
# Subscription renewal Payment insert
# =============================================================================


class TestSubscriptionRenewalPayment:
    """invoice.paid for a brand-new stripe_invoice_id creates a Payment row."""

    @pytest.mark.asyncio
    async def test_renewal_invoice_inserts_new_payment(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
        test_contact: Contact,
    ):
        """A renewal invoice_id we've never seen before creates a fresh Payment
        row attributed to the subscription's owner."""
        from src.config import settings
        original_secret = settings.STRIPE_WEBHOOK_SECRET
        settings.STRIPE_WEBHOOK_SECRET = "test-whsec"
        try:
            # Seed a StripeCustomer + Subscription owned by test_user.
            sc = StripeCustomer(
                stripe_customer_id="cus_renewal_test",
                email="renewal@test.com",
                name="Renewal Customer",
                contact_id=test_contact.id,
            )
            db_session.add(sc)
            await db_session.flush()

            sub = Subscription(
                stripe_subscription_id="sub_renewal_test",
                customer_id=sc.id,
                status="active",
                owner_id=test_user.id,
                created_by_id=test_user.id,
            )
            db_session.add(sub)
            await db_session.commit()

            renewal_invoice_id = f"in_{secrets.token_hex(8)}"
            payload = json.dumps({
                "id": f"evt_{secrets.token_hex(8)}",
                "type": "invoice.paid",
                "data": {
                    "object": {
                        "id": renewal_invoice_id,
                        "customer": "cus_renewal_test",
                        "subscription": "sub_renewal_test",
                        "amount_paid": 9999,  # $99.99 in cents
                        "currency": "usd",
                    }
                },
            }).encode()
            sig = _sign_webhook(payload, "test-whsec")

            resp = await client.post(
                "/api/payments/webhook",
                content=payload,
                headers={"stripe-signature": sig, "content-type": "application/json"},
            )
            assert resp.status_code == 200, resp.text

            # Verify the renewal Payment row was inserted.
            result = await db_session.execute(
                select(Payment).where(Payment.stripe_invoice_id == renewal_invoice_id)
            )
            payment = result.scalar_one()
            assert payment.status == "succeeded"
            assert Decimal(str(payment.amount)) == Decimal("99.99")
            assert payment.currency == "USD"
            assert payment.customer_id == sc.id
            assert payment.owner_id == test_user.id
        finally:
            settings.STRIPE_WEBHOOK_SECRET = original_secret


# =============================================================================
# customer.subscription.created creates local Subscription
# =============================================================================


class TestSubscriptionCreatedHandler:
    """customer.subscription.created inserts a local Subscription row."""

    @pytest.mark.asyncio
    async def test_subscription_created_inserts_row(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
        test_contact: Contact,
    ):
        from src.config import settings
        original_secret = settings.STRIPE_WEBHOOK_SECRET
        settings.STRIPE_WEBHOOK_SECRET = "test-whsec"
        try:
            sc = StripeCustomer(
                stripe_customer_id="cus_new_sub",
                email="newsub@test.com",
                name="New Sub Customer",
                contact_id=test_contact.id,
            )
            db_session.add(sc)
            await db_session.commit()

            now = int(time.time())
            stripe_sub_id = f"sub_{secrets.token_hex(8)}"
            payload = json.dumps({
                "id": f"evt_{secrets.token_hex(8)}",
                "type": "customer.subscription.created",
                "data": {
                    "object": {
                        "id": stripe_sub_id,
                        "customer": "cus_new_sub",
                        "status": "active",
                        "current_period_start": now,
                        "current_period_end": now + 30 * 86400,
                        "cancel_at_period_end": False,
                        "items": {"data": [{"price": {"id": "price_abc"}}]},
                    }
                },
            }).encode()
            sig = _sign_webhook(payload, "test-whsec")

            resp = await client.post(
                "/api/payments/webhook",
                content=payload,
                headers={"stripe-signature": sig, "content-type": "application/json"},
            )
            assert resp.status_code == 200, resp.text

            result = await db_session.execute(
                select(Subscription).where(Subscription.stripe_subscription_id == stripe_sub_id)
            )
            sub = result.scalar_one()
            assert sub.status == "active"
            assert sub.customer_id == sc.id
            # Owner derived from linked contact's owner_id.
            assert sub.owner_id == test_user.id
            # No local Price row existed, so price_id should be None.
            assert sub.price_id is None
        finally:
            settings.STRIPE_WEBHOOK_SECRET = original_secret


# =============================================================================
# Quote / Proposal public tokens + signer email validation
# =============================================================================


class TestQuotePublicTokenEnumeration:
    """Public routes no longer accept sequential quote_number."""

    @pytest.mark.asyncio
    async def test_quote_number_is_not_a_valid_public_handle(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
        test_contact: Contact,
    ):
        """Passing the raw quote_number to /public/ returns 404.

        Previously this worked and let an attacker walk sequential IDs
        to enumerate every customer quote in the system.
        """
        quote = Quote(
            quote_number="QT-2026-ENUM-001",
            public_token=secrets.token_urlsafe(32),
            title="Enum Test Quote",
            status="sent",
            currency="USD",
            subtotal=100.0,
            total=100.0,
            contact_id=test_contact.id,
            owner_id=test_user.id,
            created_by_id=test_user.id,
        )
        db_session.add(quote)
        await db_session.commit()

        # Guessing quote_number no longer resolves.
        resp = await client.get("/api/quotes/public/QT-2026-ENUM-001")
        assert resp.status_code == 404

        # The real token does resolve.
        resp_real = await client.get(f"/api/quotes/public/{quote.public_token}")
        assert resp_real.status_code == 200

    @pytest.mark.asyncio
    async def test_short_tokens_rejected(self, client: AsyncClient):
        """Tokens under 16 chars are treated as 404 without even a DB lookup."""
        resp = await client.get("/api/quotes/public/short")
        assert resp.status_code == 404


class TestQuoteSignerEmailValidation:
    """Public quote accept must reject a signer_email that doesn't match the contact."""

    @pytest.mark.asyncio
    async def test_accept_rejects_mismatched_email(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
        test_contact: Contact,
    ):
        quote = Quote(
            quote_number="QT-2026-SIGN-001",
            public_token=secrets.token_urlsafe(32),
            title="Signer Email Test",
            status="sent",
            currency="USD",
            subtotal=500.0,
            total=500.0,
            contact_id=test_contact.id,
            owner_id=test_user.id,
            created_by_id=test_user.id,
        )
        db_session.add(quote)
        await db_session.commit()

        resp = await client.post(
            f"/api/quotes/public/{quote.public_token}/accept",
            json={
                "signer_name": "Not The Contact",
                "signer_email": "attacker@evil.com",
            },
        )
        assert resp.status_code == 400
        assert "signer email" in resp.json()["detail"].lower()

        # Correct email (matching the contact) is accepted.
        resp_ok = await client.post(
            f"/api/quotes/public/{quote.public_token}/accept",
            json={
                "signer_name": "Real Customer",
                "signer_email": test_contact.email,
            },
        )
        assert resp_ok.status_code == 200
        data = resp_ok.json()
        assert data["status"] == "accepted"

    @pytest.mark.asyncio
    async def test_accept_is_case_insensitive_on_email(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
        test_contact: Contact,
    ):
        """Email comparison is case-insensitive (Outlook capitalises for free)."""
        quote = Quote(
            quote_number="QT-2026-CASE-001",
            public_token=secrets.token_urlsafe(32),
            title="Case Email Test",
            status="sent",
            currency="USD",
            subtotal=500.0,
            total=500.0,
            contact_id=test_contact.id,
            owner_id=test_user.id,
            created_by_id=test_user.id,
        )
        db_session.add(quote)
        await db_session.commit()

        resp = await client.post(
            f"/api/quotes/public/{quote.public_token}/accept",
            json={
                "signer_name": "Real Customer",
                "signer_email": test_contact.email.upper(),
            },
        )
        assert resp.status_code == 200


class TestProposalPublicTokenEnumeration:
    """Proposal public routes keyed on public_token, not proposal_number."""

    @pytest.mark.asyncio
    async def test_proposal_number_is_not_a_valid_public_handle(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
    ):
        proposal = Proposal(
            proposal_number="PR-2026-ENUM-001",
            public_token=secrets.token_urlsafe(32),
            title="Enum Test Proposal",
            status="sent",
            owner_id=test_user.id,
            created_by_id=test_user.id,
        )
        db_session.add(proposal)
        await db_session.commit()

        # proposal_number does not resolve.
        resp = await client.get("/api/proposals/public/PR-2026-ENUM-001")
        assert resp.status_code == 404

        # public_token does.
        resp_ok = await client.get(f"/api/proposals/public/{proposal.public_token}")
        assert resp_ok.status_code == 200


# =============================================================================
# Google OAuth state cookie CSRF defense
# =============================================================================


class TestGoogleOAuthStateCookie:
    """Server-side state cookie verification on /auth/google/callback."""

    @pytest.mark.asyncio
    async def test_callback_without_state_cookie_rejected(self, client: AsyncClient):
        """Callback POST without a matching cookie state is rejected 400.

        Previously the state check was client-only (sessionStorage). A
        victim lured to /callback directly has no cookie, so the new
        server check rejects before we ever call Google.
        """
        from src.config import settings

        original_id = settings.GOOGLE_CLIENT_ID
        original_secret = settings.GOOGLE_CLIENT_SECRET
        settings.GOOGLE_CLIENT_ID = "test-client-id.apps.googleusercontent.com"
        settings.GOOGLE_CLIENT_SECRET = "test-client-secret"
        try:
            resp = await client.post(
                "/api/auth/google/callback",
                json={
                    "code": "anything",
                    "redirect_uri": "http://localhost:3000/auth/google/callback",
                    "state": "attacker-forged-state",
                },
            )
            assert resp.status_code == 400
            assert "state mismatch" in resp.json()["detail"].lower()
        finally:
            settings.GOOGLE_CLIENT_ID = original_id
            settings.GOOGLE_CLIENT_SECRET = original_secret

    @pytest.mark.asyncio
    async def test_authorize_sets_httponly_cookie(self, client: AsyncClient):
        """/authorize sets the state cookie as HttpOnly + SameSite=Lax."""
        from src.config import settings

        original_id = settings.GOOGLE_CLIENT_ID
        settings.GOOGLE_CLIENT_ID = "test-client-id.apps.googleusercontent.com"
        try:
            resp = await client.post(
                "/api/auth/google/authorize",
                json={"redirect_uri": "http://localhost:3000/auth/google/callback"},
            )
            assert resp.status_code == 200
            # Starlette sets cookies via Set-Cookie; httpx exposes via response.cookies
            raw = resp.headers.get("set-cookie", "")
            assert "crm_google_oauth_state=" in raw
            assert "HttpOnly" in raw
            assert "SameSite=lax" in raw.lower() or "samesite=lax" in raw.lower()
        finally:
            settings.GOOGLE_CLIENT_ID = original_id
