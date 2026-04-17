"""Stripe webhook processing logic.

Extracted from service.py so that PaymentService stays focused on CRUD.
All webhook-related methods live here; PaymentService delegates to this
class via thin forwarding methods to preserve backward compatibility.
"""

import hashlib
import hmac
import json
import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.payments.models import (
    Payment,
    Price,
    Subscription,
    StripeCustomer,
)
from src.webhooks.stripe_events import WebhookEvent

logger = logging.getLogger(__name__)


class WebhookProcessor:
    """Handles Stripe webhook signature verification and event dispatching.

    Takes a database session in __init__ (same pattern as PaymentService).
    Callers should call process_webhook() for end-to-end handling, or
    individual _handle_* methods for targeted testing.
    """

    # Stripe recommends 5-minute tolerance between payload timestamp and now
    # to defend against captured-payload replays.
    WEBHOOK_TIMESTAMP_TOLERANCE_SECONDS = 300

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    async def process_webhook(self, payload: bytes, sig_header: str) -> dict:
        """Process a Stripe webhook event.

        Verifies the signature + freshness (5 min tolerance) then dedups
        by the Stripe event_id against the webhook_events table. Replayed
        payloads return a "replayed: True" marker without re-running
        handlers.

        Raises ValueError on invalid signature, stale timestamp, or
        missing config.
        """
        # Deferred module import (not `from ... import`) so tests can patch
        # `src.payments.service.settings` and `_get_stripe` and have the
        # patches take effect here via Python's sys.modules cache.
        import src.payments.service as _svc_mod
        _settings = _svc_mod.settings
        webhook_secret = getattr(_settings, "STRIPE_WEBHOOK_SECRET", "")
        if not webhook_secret:
            raise ValueError("Stripe webhook secret is not configured.")

        # Prefer the official stripe.Webhook.construct_event when the
        # library is installed: it does signature + timestamp tolerance
        # in one shot and rejects both stale and tampered payloads. Fall
        # back to our hand-rolled HMAC verify when stripe isn't available
        # (e.g. unit tests running without the package) so callers still
        # get signature verification — but still enforce a timestamp
        # tolerance using the t=<unix> field.
        event_id: str
        event_type: str
        obj: dict
        event: dict

        stripe = _svc_mod._get_stripe()
        if stripe is not None:
            try:
                event = stripe.Webhook.construct_event(
                    payload,
                    sig_header,
                    webhook_secret,
                    tolerance=self.WEBHOOK_TIMESTAMP_TOLERANCE_SECONDS,
                )
            except Exception as exc:
                raise ValueError(f"Invalid webhook: {exc}") from exc
            # `event` behaves as a mapping; normalize for the rest of the
            # code path which expects dict lookups.
            event_id = event["id"]
            event_type = event["type"]
            obj = event["data"]["object"]
        else:
            if not self._verify_webhook_signature(
                payload, sig_header, webhook_secret,
                tolerance=self.WEBHOOK_TIMESTAMP_TOLERANCE_SECONDS,
            ):
                raise ValueError("Invalid webhook signature.")
            event_data = json.loads(payload)
            event_id = event_data.get("id", "")
            event_type = event_data.get("type", "")
            obj = event_data.get("data", {}).get("object", {})

        # Dedup: skip replays (same event_id seen previously).
        if event_id:
            seen = await self.db.execute(
                select(WebhookEvent).where(WebhookEvent.event_id == event_id)
            )
            if seen.scalar_one_or_none() is not None:
                return {
                    "event_type": event_type,
                    "event_id": event_id,
                    "status": "replayed",
                }

        if event_type == "checkout.session.completed":
            await self._handle_checkout_completed(obj)
        elif event_type == "payment_intent.succeeded":
            await self._handle_payment_succeeded(obj)
        elif event_type == "payment_intent.payment_failed":
            await self._handle_payment_failed(obj)
        elif event_type == "charge.refunded":
            await self._handle_charge_refunded(obj)
        elif event_type == "customer.subscription.created":
            await self._handle_subscription_created(obj)
        elif event_type == "customer.subscription.updated":
            await self._handle_subscription_updated(obj)
        elif event_type == "customer.subscription.deleted":
            await self._handle_subscription_deleted(obj)
        elif event_type == "invoice.paid":
            await self._handle_invoice_paid(obj)
        elif event_type == "invoice.payment_failed":
            await self._handle_invoice_payment_failed(obj)
        elif event_type == "invoice.sent":
            await self._handle_invoice_sent(obj)
        elif event_type == "checkout.session.async_payment_succeeded":
            await self._handle_async_payment_succeeded(obj)
        elif event_type == "checkout.session.async_payment_failed":
            await self._handle_async_payment_failed(obj)
        elif event_type == "setup_intent.succeeded":
            await self._handle_setup_intent_succeeded(obj)

        # Mark processed AFTER all handlers ran so a mid-processing crash
        # allows Stripe to retry. The dedup above still protects against
        # the common case of duplicate deliveries from Stripe's own retry
        # machinery.
        if event_id:
            self.db.add(
                WebhookEvent(event_id=event_id, event_type=event_type or "unknown")
            )
            await self.db.flush()

        return {"event_type": event_type, "event_id": event_id, "status": "processed"}

    # ------------------------------------------------------------------
    # Signature verification
    # ------------------------------------------------------------------

    @staticmethod
    def _verify_webhook_signature(
        payload: bytes,
        sig_header: str,
        secret: str,
        tolerance: int = 300,
    ) -> bool:
        """Verify Stripe webhook HMAC-SHA256 signature with timestamp
        tolerance. Stripe sends the signature as ``t=<unix>,v1=<hex>``.

        Returns False on malformed header, bad signature, OR a timestamp
        more than `tolerance` seconds old (or in the future).
        """
        try:
            elements = dict(
                pair.split("=", 1) for pair in sig_header.split(",") if "=" in pair
            )
            timestamp = elements.get("t", "")
            signature = elements.get("v1", "")

            if not timestamp or not signature:
                return False

            # Reject stale / future-dated payloads.
            try:
                payload_ts = int(timestamp)
            except ValueError:
                return False
            now_ts = int(datetime.now(timezone.utc).timestamp())
            if abs(now_ts - payload_ts) > tolerance:
                return False

            # Compute expected signature
            signed_payload = f"{timestamp}.".encode() + payload
            expected = hmac.new(
                secret.encode(), signed_payload, hashlib.sha256
            ).hexdigest()

            return hmac.compare_digest(expected, signature)
        except (ValueError, KeyError, TypeError) as exc:
            logger.warning("Webhook signature verification failed: %s", exc)
            return False

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _find_payment(self, lookup_field, obj: dict, obj_key: str = "id") -> Optional[Payment]:
        """Look up a Payment by a Stripe ID field. Returns None if not found."""
        value = obj.get(obj_key)
        if not value:
            return None
        result = await self.db.execute(
            select(Payment).where(lookup_field == value)
        )
        return result.scalar_one_or_none()

    async def _set_payment_status(
        self, payment: Optional[Payment], new_status: str,
        guard_statuses: tuple = ("succeeded", "refunded"),
    ) -> None:
        """Set payment status if payment exists and current status is not in guard_statuses."""
        if not payment:
            return
        if guard_statuses and payment.status in guard_statuses:
            return
        payment.status = new_status
        await self.db.flush()

    async def _send_payment_receipt(self, payment_id: int) -> None:
        """Delegate to PaymentService.send_payment_receipt to avoid duplicating logic."""
        from src.payments.service import PaymentService
        svc = PaymentService(self.db)
        await svc.send_payment_receipt(payment_id)

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------

    async def _handle_checkout_completed(self, session_obj: dict) -> None:
        """Handle checkout.session.completed event.

        For ACH/bank payments, payment_status may be "processing" rather than
        "paid". In that case we set status to "processing" and do NOT send
        receipt -- the receipt is sent when async_payment_succeeded fires.
        """
        session_id = session_obj.get("id")
        if not session_id:
            return

        result = await self.db.execute(
            select(Payment).where(Payment.stripe_checkout_session_id == session_id)
        )
        payment = result.scalar_one_or_none()
        if payment and payment.status not in ("succeeded", "refunded"):
            payment_intent_id = session_obj.get("payment_intent")
            if payment_intent_id:
                payment.stripe_payment_intent_id = payment_intent_id

            payment_status = session_obj.get("payment_status")
            if payment_status == "processing":
                payment.status = "processing"
                await self.db.flush()
            else:
                payment.status = "succeeded"
                await self.db.flush()

                # Send branded receipt email only when fully paid
                try:
                    await self._send_payment_receipt(payment.id)
                except (OSError, RuntimeError) as exc:
                    logger.warning("Failed to send receipt for payment %s: %s", payment.id, exc)

    async def _handle_payment_succeeded(self, intent_obj: dict) -> None:
        """Handle payment_intent.succeeded event."""
        intent_id = intent_obj.get("id")
        if not intent_id:
            return

        result = await self.db.execute(
            select(Payment).where(Payment.stripe_payment_intent_id == intent_id)
        )
        payment = result.scalar_one_or_none()
        if payment and payment.status != "succeeded":
            payment.status = "succeeded"
            charge = None
            charges = intent_obj.get("charges", {}).get("data", [])
            if charges:
                charge = charges[0]
            elif isinstance(intent_obj.get("latest_charge"), dict):
                charge = intent_obj["latest_charge"]
            if charge:
                payment.receipt_url = charge.get("receipt_url")
                payment.payment_method = charge.get("payment_method_details", {}).get("type")
            await self.db.flush()

            # Send branded receipt email
            try:
                await self._send_payment_receipt(payment.id)
            except (OSError, RuntimeError) as exc:
                logger.warning("Failed to send receipt for payment %s: %s", payment.id, exc)

    async def _handle_payment_failed(self, intent_obj: dict) -> None:
        """Handle payment_intent.payment_failed event."""
        payment = await self._find_payment(Payment.stripe_payment_intent_id, intent_obj)
        await self._set_payment_status(payment, "failed")

    async def _handle_charge_refunded(self, charge_obj: dict) -> None:
        """Handle charge.refunded event."""
        payment = await self._find_payment(
            Payment.stripe_payment_intent_id, charge_obj, obj_key="payment_intent"
        )
        await self._set_payment_status(payment, "refunded", guard_statuses=())

    async def _handle_subscription_created(self, sub_obj: dict) -> None:
        """Handle customer.subscription.created — insert local Subscription
        row so the table actually reflects what Stripe has.

        Before this fix no handler ran on subscription.created (it was
        collapsed into subscription.updated which only did UPDATEs), so
        subscriptions created via Stripe Checkout were silently missing
        from the local database forever.
        """
        sub_id = sub_obj.get("id")
        if not sub_id:
            return

        # Dedup: if we already have this subscription, fall through to
        # the updated handler so we still refresh mutable fields.
        existing = await self.db.execute(
            select(Subscription).where(Subscription.stripe_subscription_id == sub_id)
        )
        if existing.scalar_one_or_none() is not None:
            await self._handle_subscription_updated(sub_obj)
            return

        # Resolve the local StripeCustomer by Stripe's customer id.
        stripe_customer_id = sub_obj.get("customer")
        customer_row = None
        if stripe_customer_id:
            cust_result = await self.db.execute(
                select(StripeCustomer).where(
                    StripeCustomer.stripe_customer_id == stripe_customer_id
                )
            )
            customer_row = cust_result.scalar_one_or_none()
        if customer_row is None:
            logger.warning(
                "subscription.created for unknown customer %s — skipping local row insert",
                stripe_customer_id,
            )
            return

        # Derive owner_id from the linked contact/company so admin lists
        # still work with the new row.
        owner_id = None
        if customer_row.contact and customer_row.contact.owner_id:
            owner_id = customer_row.contact.owner_id
        elif customer_row.company and customer_row.company.owner_id:
            owner_id = customer_row.company.owner_id

        # Optional: resolve local Price if we happen to have one matching
        # the Stripe price id. `price_id` is now nullable (migration 003)
        # so the miss case is fine.
        local_price_id = None
        items = (sub_obj.get("items") or {}).get("data") or []
        if items:
            stripe_price_id = (items[0].get("price") or {}).get("id")
            if stripe_price_id:
                price_result = await self.db.execute(
                    select(Price).where(Price.stripe_price_id == stripe_price_id)
                )
                local_price = price_result.scalar_one_or_none()
                if local_price is not None:
                    local_price_id = local_price.id

        def _ts_to_dt(ts):
            if ts is None:
                return None
            return datetime.fromtimestamp(int(ts), tz=timezone.utc)

        subscription = Subscription(
            stripe_subscription_id=sub_id,
            customer_id=customer_row.id,
            price_id=local_price_id,
            status=sub_obj.get("status") or "active",
            current_period_start=_ts_to_dt(sub_obj.get("current_period_start")),
            current_period_end=_ts_to_dt(sub_obj.get("current_period_end")),
            cancel_at_period_end=bool(sub_obj.get("cancel_at_period_end")),
            owner_id=owner_id,
            created_by_id=owner_id,
        )
        self.db.add(subscription)
        await self.db.flush()

    async def _handle_subscription_updated(self, sub_obj: dict) -> None:
        """Handle customer.subscription.updated — refresh mutable fields."""
        sub_id = sub_obj.get("id")
        if not sub_id:
            return

        result = await self.db.execute(
            select(Subscription).where(Subscription.stripe_subscription_id == sub_id)
        )
        subscription = result.scalar_one_or_none()
        if subscription:
            subscription.status = sub_obj.get("status", subscription.status)
            subscription.cancel_at_period_end = sub_obj.get(
                "cancel_at_period_end", subscription.cancel_at_period_end
            )
            await self.db.flush()

    async def _handle_subscription_deleted(self, sub_obj: dict) -> None:
        """Handle subscription deleted event."""
        sub_id = sub_obj.get("id")
        if not sub_id:
            return

        result = await self.db.execute(
            select(Subscription).where(Subscription.stripe_subscription_id == sub_id)
        )
        subscription = result.scalar_one_or_none()
        if subscription:
            subscription.status = "canceled"
            await self.db.flush()

    async def _handle_invoice_paid(self, invoice_obj: dict) -> None:
        """Handle invoice.paid — covers both initial invoices we created
        in-app and Stripe-initiated subscription renewal invoices.

        For the first case, mark the existing Payment row succeeded.
        For subscription renewals, the invoice ID is brand new to us, so
        insert a fresh Payment row linked to the matching Subscription —
        otherwise recurring revenue is silently dropped.
        """
        invoice_id = invoice_obj.get("id")
        if not invoice_id:
            return

        result = await self.db.execute(
            select(Payment).where(Payment.stripe_invoice_id == invoice_id)
        )
        payment = result.scalar_one_or_none()
        if payment is not None:
            if payment.status != "succeeded":
                payment.status = "succeeded"
                await self.db.flush()
            return

        # ------------------------------------------------------------------
        # Subscription renewal path: no existing Payment row for this
        # invoice. Try to attach to a local Subscription + StripeCustomer
        # and create a new Payment so MRR/ARR reporting stays correct.
        # ------------------------------------------------------------------
        stripe_subscription_id = invoice_obj.get("subscription")
        subscription = None
        if stripe_subscription_id:
            sub_result = await self.db.execute(
                select(Subscription).where(
                    Subscription.stripe_subscription_id == stripe_subscription_id
                )
            )
            subscription = sub_result.scalar_one_or_none()

        stripe_customer_id = invoice_obj.get("customer")
        customer_row = None
        if stripe_customer_id:
            cust_result = await self.db.execute(
                select(StripeCustomer).where(
                    StripeCustomer.stripe_customer_id == stripe_customer_id
                )
            )
            customer_row = cust_result.scalar_one_or_none()

        if subscription is None and customer_row is None:
            # Nothing to link to — log and drop instead of inserting an
            # orphan Payment row.
            logger.warning(
                "invoice.paid for unknown invoice %s with no matching subscription/customer",
                invoice_id,
            )
            return

        owner_id = None
        if subscription is not None:
            owner_id = subscription.owner_id
        if owner_id is None and customer_row is not None:
            if customer_row.contact and customer_row.contact.owner_id:
                owner_id = customer_row.contact.owner_id
            elif customer_row.company and customer_row.company.owner_id:
                owner_id = customer_row.company.owner_id

        amount_cents = invoice_obj.get("amount_paid") or invoice_obj.get("total") or 0
        amount_dollars = (Decimal(int(amount_cents)) / Decimal("100")).quantize(
            Decimal("0.01")
        )
        currency = (invoice_obj.get("currency") or "usd").upper()

        renewal_payment = Payment(
            stripe_invoice_id=invoice_id,
            amount=amount_dollars,
            currency=currency,
            status="succeeded",
            customer_id=customer_row.id if customer_row else None,
            owner_id=owner_id,
            created_by_id=owner_id,
        )
        try:
            async with self.db.begin_nested():
                self.db.add(renewal_payment)
                await self.db.flush()
        except Exception as exc:
            logger.warning(
                "invoice.paid renewal insert race for %s: %s", invoice_id, exc
            )

    async def _handle_invoice_payment_failed(self, invoice_obj: dict) -> None:
        """Handle invoice.payment_failed event -- marks payment as failed."""
        invoice_id = invoice_obj.get("id")
        if not invoice_id:
            return

        result = await self.db.execute(
            select(Payment).where(Payment.stripe_invoice_id == invoice_id)
        )
        payment = result.scalar_one_or_none()
        if payment and payment.status not in ("succeeded", "refunded"):
            payment.status = "failed"
            await self.db.flush()

    async def _handle_invoice_sent(self, invoice_obj: dict) -> None:
        """Handle invoice.sent event -- marks pending payment as sent."""
        invoice_id = invoice_obj.get("id")
        if not invoice_id:
            return

        result = await self.db.execute(
            select(Payment).where(Payment.stripe_invoice_id == invoice_id)
        )
        payment = result.scalar_one_or_none()
        if payment and payment.status == "pending":
            payment.status = "sent"
            await self.db.flush()

    async def _handle_async_payment_succeeded(self, session_obj: dict) -> None:
        """Handle checkout.session.async_payment_succeeded (ACH success)."""
        session_id = session_obj.get("id")
        if not session_id:
            return

        result = await self.db.execute(
            select(Payment).where(Payment.stripe_checkout_session_id == session_id)
        )
        payment = result.scalar_one_or_none()
        if payment and payment.status != "succeeded":
            payment.status = "succeeded"
            payment_intent_id = session_obj.get("payment_intent")
            if payment_intent_id:
                payment.stripe_payment_intent_id = payment_intent_id
            await self.db.flush()

            try:
                await self._send_payment_receipt(payment.id)
            except (OSError, RuntimeError) as exc:
                logger.warning("Failed to send receipt for payment %s: %s", payment.id, exc)

    async def _handle_async_payment_failed(self, session_obj: dict) -> None:
        """Handle checkout.session.async_payment_failed (ACH failure)."""
        session_id = session_obj.get("id")
        if not session_id:
            return

        result = await self.db.execute(
            select(Payment).where(Payment.stripe_checkout_session_id == session_id)
        )
        payment = result.scalar_one_or_none()
        if payment and payment.status not in ("succeeded", "refunded"):
            payment.status = "failed"
            await self.db.flush()

    async def _handle_setup_intent_succeeded(self, setup_obj: dict) -> None:
        """Handle setup_intent.succeeded -- log for future payment method reuse."""
        setup_id = setup_obj.get("id")
        customer_id = setup_obj.get("customer")
        logger.info(
            "SetupIntent succeeded: %s for customer %s", setup_id, customer_id
        )
