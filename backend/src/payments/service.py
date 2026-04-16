"""Payment service layer."""

import hashlib
import hmac
import json
import logging
import uuid
from decimal import Decimal, ROUND_HALF_UP
from datetime import datetime, timezone
from html import escape
from typing import Optional, List, Tuple, Union

from sqlalchemy import select, func, or_, String
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.payments.models import (
    StripeCustomer,
    Product,
    Price,
    Payment,
    Subscription,
)
from src.payments.schemas import (
    PaymentCreate,
    PaymentUpdate,
    ProductCreate,
    ProductUpdate,
    PriceCreate,
    StripeCustomerCreate,
)
from src.webhooks.stripe_events import WebhookEvent
from src.core.base_service import CRUDService
from src.core.constants import DEFAULT_PAGE_SIZE
from src.config import settings


# Common: rounding money to integer cents. Stripe expects amounts as ints.
# Use banker's-rounding-free half-up so $19.995 → 2000¢, not 1999¢.
def _to_cents(amount: Union[float, int, Decimal, str]) -> int:
    """Convert a user-facing money amount to integer cents.

    Uses Decimal + ROUND_HALF_UP so values like 19.995 round to 2000
    (not 1999, which is what naive int/truncation produces).
    """
    dec = amount if isinstance(amount, Decimal) else Decimal(str(amount))
    cents = (dec * Decimal("100")).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return int(cents)

logger = logging.getLogger(__name__)


def _get_stripe():
    """Lazily import and configure stripe module.

    Returns the stripe module if STRIPE_SECRET_KEY is configured,
    otherwise returns None.
    """
    stripe_key = getattr(settings, "STRIPE_SECRET_KEY", "")
    if not stripe_key:
        return None
    try:
        import stripe
        stripe.api_key = stripe_key
        return stripe
    except ImportError:
        logger.warning("stripe package not installed")
        return None


class PaymentService(CRUDService[Payment, PaymentCreate, PaymentUpdate]):
    """Service for Payment CRUD operations and Stripe integration."""

    model = Payment
    create_exclude_fields: set = set()
    update_exclude_fields: set = set()

    def _get_eager_load_options(self):
        return [
            selectinload(Payment.customer),
            selectinload(Payment.opportunity),
            selectinload(Payment.quote),
        ]

    async def get_list(
        self,
        page: int = 1,
        page_size: int = DEFAULT_PAGE_SIZE,
        status: Optional[str] = None,
        customer_id: Optional[int] = None,
        owner_id: Optional[int] = None,
        shared_entity_ids: Optional[List[int]] = None,
        search: Optional[str] = None,
    ) -> Tuple[List[Payment], int]:
        """Get paginated list of payments with filters."""
        query = (
            select(Payment)
            .options(
                selectinload(Payment.customer),
                selectinload(Payment.opportunity),
                selectinload(Payment.quote),
            )
        )

        if status:
            query = query.where(Payment.status == status)

        if customer_id:
            query = query.where(Payment.customer_id == customer_id)

        if owner_id:
            if shared_entity_ids:
                query = query.where(
                    or_(Payment.owner_id == owner_id, Payment.id.in_(shared_entity_ids))
                )
            else:
                query = query.where(Payment.owner_id == owner_id)

        if search:
            search_term = f"%{search}%"
            query = query.join(Payment.customer, isouter=True).where(
                or_(
                    StripeCustomer.name.ilike(search_term),
                    StripeCustomer.email.ilike(search_term),
                    func.cast(Payment.amount, String).like(search_term),
                    Payment.status.ilike(search_term),
                )
            )

        count_query = select(func.count()).select_from(query.subquery())
        total_result = await self.db.execute(count_query)
        total = total_result.scalar() or 0

        offset = (page - 1) * page_size
        query = query.offset(offset).limit(page_size).order_by(Payment.created_at.desc())

        result = await self.db.execute(query)
        payments = list(result.scalars().all())

        return payments, total

    # Mapping from quote recurring_interval to Stripe interval
    INTERVAL_MAP = {
        "monthly": "month",
        "quarterly": "month",
        "yearly": "year",
    }
    INTERVAL_COUNT_MAP = {
        "monthly": 1,
        "quarterly": 3,
        "yearly": 1,
    }

    async def create_checkout_session(
        self,
        amount: float,
        currency: str,
        success_url: str,
        cancel_url: str,
        user_id: int,
        customer_id: Optional[int] = None,
        quote_id: Optional[int] = None,
    ) -> dict:
        """Create a Stripe Checkout Session.

        If the linked quote has payment_type="subscription", creates a
        subscription-mode checkout session using the quote's recurring_interval.
        Supports card and ACH (us_bank_account) payment methods.

        Returns dict with checkout_session_id and checkout_url,
        or raises ValueError if Stripe is not configured.
        """
        stripe = _get_stripe()
        if not stripe:
            raise ValueError("Stripe is not configured. Set STRIPE_SECRET_KEY environment variable.")

        # Resolve Stripe customer ID if we have a local customer
        stripe_customer_id = None
        if customer_id:
            cust = await self.db.execute(
                select(StripeCustomer).where(StripeCustomer.id == customer_id)
            )
            customer = cust.scalar_one_or_none()
            if customer:
                stripe_customer_id = customer.stripe_customer_id

        # Check if quote is subscription type
        is_subscription = False
        recurring_interval = None
        if quote_id:
            from src.quotes.models import Quote
            quote_result = await self.db.execute(
                select(Quote).where(Quote.id == quote_id)
            )
            quote = quote_result.scalar_one_or_none()
            if quote and quote.payment_type == "subscription":
                is_subscription = True
                recurring_interval = quote.recurring_interval

        # Get tenant branding for company name in checkout description
        company_name = "CRM"
        if user_id:
            try:
                from src.email.branded_templates import TenantBrandingHelper
                branding = await TenantBrandingHelper.get_branding_for_user(
                    self.db, user_id
                )
                company_name = branding.get("company_name", "CRM")
            except (ImportError, LookupError, OSError) as exc:
                logger.debug("Could not load tenant branding: %s", exc)

        # Build price_data based on payment type
        price_data: dict = {
            "currency": currency.lower(),
            "product_data": {"name": f"Payment to {company_name} - {currency} {amount}"},
            "unit_amount": _to_cents(amount),
        }

        if is_subscription and recurring_interval:
            stripe_interval = self.INTERVAL_MAP.get(recurring_interval, "month")
            interval_count = self.INTERVAL_COUNT_MAP.get(recurring_interval, 1)
            price_data["recurring"] = {
                "interval": stripe_interval,
                "interval_count": interval_count,
            }

        checkout_mode = "subscription" if is_subscription else "payment"

        session_params = {
            "payment_method_types": ["card", "us_bank_account"],
            "line_items": [{"price_data": price_data, "quantity": 1}],
            "mode": checkout_mode,
            "success_url": success_url,
            "cancel_url": cancel_url,
            "payment_method_options": {
                "us_bank_account": {
                    "financial_connections": {"permissions": ["payment_method"]},
                },
            },
        }
        if stripe_customer_id:
            session_params["customer"] = stripe_customer_id
        if checkout_mode == "payment":
            session_params["payment_intent_data"] = {"setup_future_usage": "off_session"}

        session = stripe.checkout.Session.create(**session_params)

        # Create local payment record
        payment = Payment(
            stripe_checkout_session_id=session.id,
            amount=amount,
            currency=currency.upper(),
            status="pending",
            customer_id=customer_id,
            quote_id=quote_id,
            owner_id=user_id,
            created_by_id=user_id,
        )
        self.db.add(payment)
        await self.db.flush()

        return {
            "checkout_session_id": session.id,
            "checkout_url": session.url,
        }

    async def create_payment_intent(
        self,
        amount: float,
        currency: str,
        user_id: int,
        customer_id: Optional[int] = None,
        opportunity_id: Optional[int] = None,
        quote_id: Optional[int] = None,
    ) -> dict:
        """Create a Stripe PaymentIntent.

        Returns dict with payment_intent_id, client_secret, and payment_id,
        or raises ValueError if Stripe is not configured.
        """
        stripe = _get_stripe()
        if not stripe:
            raise ValueError("Stripe is not configured. Set STRIPE_SECRET_KEY environment variable.")

        # Resolve Stripe customer ID
        stripe_customer_id = None
        if customer_id:
            cust = await self.db.execute(
                select(StripeCustomer).where(StripeCustomer.id == customer_id)
            )
            customer = cust.scalar_one_or_none()
            if customer:
                stripe_customer_id = customer.stripe_customer_id

        intent_params = {
            "amount": _to_cents(amount),
            "currency": currency.lower(),
        }
        if stripe_customer_id:
            intent_params["customer"] = stripe_customer_id

        intent = stripe.PaymentIntent.create(**intent_params)

        # Create local payment record
        payment = Payment(
            stripe_payment_intent_id=intent.id,
            amount=amount,
            currency=currency.upper(),
            status="pending",
            customer_id=customer_id,
            opportunity_id=opportunity_id,
            quote_id=quote_id,
            owner_id=user_id,
            created_by_id=user_id,
        )
        self.db.add(payment)
        await self.db.flush()
        await self.db.refresh(payment)

        return {
            "payment_intent_id": intent.id,
            "client_secret": intent.client_secret,
            "payment_id": payment.id,
        }

    async def sync_customer(
        self,
        contact_id: Optional[int] = None,
        company_id: Optional[int] = None,
        email: Optional[str] = None,
        name: Optional[str] = None,
    ) -> StripeCustomer:
        """Sync a CRM contact/company to a Stripe customer.

        If a local StripeCustomer already exists for the given contact/company,
        returns the existing record. Otherwise creates a new Stripe customer
        (if Stripe is configured) or a local-only record.
        """
        # Check if we already have a StripeCustomer for this entity
        if contact_id:
            result = await self.db.execute(
                select(StripeCustomer).where(StripeCustomer.contact_id == contact_id)
            )
            existing = result.scalar_one_or_none()
            if existing:
                return existing

        if company_id:
            result = await self.db.execute(
                select(StripeCustomer).where(StripeCustomer.company_id == company_id)
            )
            existing = result.scalar_one_or_none()
            if existing:
                return existing

        # Resolve email/name from contact or company if not provided
        if contact_id and not email:
            from src.contacts.models import Contact
            contact_result = await self.db.execute(
                select(Contact).where(Contact.id == contact_id)
            )
            contact = contact_result.scalar_one_or_none()
            if contact:
                email = email or contact.email
                name = name or getattr(contact, "full_name", None)

        if company_id and not email:
            from src.companies.models import Company
            company_result = await self.db.execute(
                select(Company).where(Company.id == company_id)
            )
            company = company_result.scalar_one_or_none()
            if company:
                email = email or company.email
                name = name or company.name

        # Try to create Stripe customer
        stripe = _get_stripe()
        stripe_customer_id = None
        if stripe:
            stripe_params = {}
            if email:
                stripe_params["email"] = email
            if name:
                stripe_params["name"] = name
            stripe_cust = stripe.Customer.create(**stripe_params)
            stripe_customer_id = stripe_cust.id
        else:
            stripe_customer_id = f"local_{uuid.uuid4().hex[:16]}"

        customer = StripeCustomer(
            contact_id=contact_id,
            company_id=company_id,
            stripe_customer_id=stripe_customer_id,
            email=email,
            name=name,
        )
        self.db.add(customer)
        await self.db.flush()
        await self.db.refresh(customer)
        return customer

    # Stripe recommends 5-minute tolerance between payload timestamp and now
    # to defend against captured-payload replays. Our own constant so tests
    # can override it if needed.
    WEBHOOK_TIMESTAMP_TOLERANCE_SECONDS = 300

    async def process_webhook(self, payload: bytes, sig_header: str) -> dict:
        """Process a Stripe webhook event.

        Verifies the signature + freshness (5 min tolerance) then dedups
        by the Stripe event_id against the webhook_events table. Replayed
        payloads return a "replayed: True" marker without re-running
        handlers.

        Raises ValueError on invalid signature, stale timestamp, or
        missing config.
        """
        webhook_secret = getattr(settings, "STRIPE_WEBHOOK_SECRET", "")
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

        stripe = _get_stripe()
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

    async def send_payment_receipt(self, payment_id: int) -> None:
        """Send branded receipt email after successful payment."""
        from src.email.branded_templates import (
            TenantBrandingHelper,
            render_payment_receipt_email,
        )
        from src.email.service import EmailService

        result = await self.db.execute(
            select(Payment)
            .options(
                selectinload(Payment.customer),
                selectinload(Payment.quote),
            )
            .where(Payment.id == payment_id)
        )
        payment = result.scalar_one_or_none()
        if not payment:
            return

        # Determine recipient email
        to_email = None
        client_name = "Customer"
        if payment.customer:
            to_email = payment.customer.email
            client_name = payment.customer.name or client_name
        if not to_email:
            return

        # Get tenant branding
        branding = TenantBrandingHelper.get_default_branding()
        if payment.owner_id:
            branding = await TenantBrandingHelper.get_branding_for_user(
                self.db, payment.owner_id
            )

        payment_data = {
            "receipt_number": str(payment.id),
            "client_name": client_name,
            "amount": str(payment.amount),
            "currency": payment.currency,
            "payment_date": payment.updated_at.strftime("%Y-%m-%d") if payment.updated_at else "",
            "payment_method": payment.payment_method or "Card",
        }

        subject, html_body = render_payment_receipt_email(branding, payment_data)

        email_service = EmailService(self.db)
        await email_service.queue_email(
            to_email=to_email,
            subject=subject,
            body=html_body,
            sent_by_id=payment.owner_id,
            entity_type="payments",
            entity_id=payment.id,
        )

    async def generate_invoice_pdf(self, payment_id: int) -> bytes:
        """Generate branded invoice PDF for a payment.

        Returns PDF bytes as a simple HTML-to-bytes representation.
        Uses the branded template to create a printable invoice.
        """
        from src.email.branded_templates import TenantBrandingHelper

        result = await self.db.execute(
            select(Payment)
            .options(
                selectinload(Payment.customer),
                selectinload(Payment.quote),
                selectinload(Payment.opportunity),
            )
            .where(Payment.id == payment_id)
        )
        payment = result.scalar_one_or_none()
        if not payment:
            raise ValueError(f"Payment {payment_id} not found")

        branding = TenantBrandingHelper.get_default_branding()
        if payment.owner_id:
            branding = await TenantBrandingHelper.get_branding_for_user(
                self.db, payment.owner_id
            )

        company = escape(branding.get("company_name", "CRM"))
        primary = escape(branding.get("primary_color", "#6366f1"))
        logo_url = branding.get("logo_url", "")
        footer_text = escape(branding.get("footer_text", ""))

        client_name = "Customer"
        client_email = ""
        if payment.customer:
            client_name = escape(payment.customer.name or "Customer")
            client_email = escape(payment.customer.email or "")

        pay_date = ""
        if payment.updated_at:
            pay_date = payment.updated_at.strftime("%Y-%m-%d")

        logo_html = ""
        if logo_url:
            logo_html = (
                f'<img src="{escape(logo_url)}" alt="{company}" '
                f'width="40" height="40" style="margin-right:12px;border-radius:6px;" />'
            )

        html = f"""\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<title>Invoice #{payment.id}</title>
<style>
body {{ font-family: Arial, Helvetica, sans-serif; margin: 40px; color: #111827; }}
.header {{ display: flex; justify-content: space-between; align-items: center; border-bottom: 3px solid {primary}; padding-bottom: 16px; margin-bottom: 24px; }}
.company {{ font-size: 20px; font-weight: 700; color: {primary}; }}
.invoice-title {{ font-size: 28px; font-weight: 700; color: #111827; margin-bottom: 4px; }}
.meta-table {{ width: 100%; margin-bottom: 24px; }}
.meta-table td {{ padding: 4px 8px; font-size: 14px; }}
.meta-label {{ color: #6b7280; font-weight: 600; width: 140px; }}
.items-table {{ width: 100%; border-collapse: collapse; margin-bottom: 24px; }}
.items-table th {{ background-color: #f9fafb; padding: 10px 12px; text-align: left; font-size: 13px; font-weight: 600; color: #6b7280; border-bottom: 2px solid #e5e7eb; }}
.items-table td {{ padding: 10px 12px; border-bottom: 1px solid #e5e7eb; font-size: 14px; }}
.total-row td {{ font-weight: 700; font-size: 16px; border-top: 2px solid #111827; }}
.amount-col {{ text-align: right; font-variant-numeric: tabular-nums; }}
.footer {{ margin-top: 40px; padding-top: 16px; border-top: 1px solid #e5e7eb; text-align: center; font-size: 12px; color: #9ca3af; }}
@media print {{ body {{ margin: 20px; }} }}
</style>
</head>
<body>
<div class="header">
  <div>
    <div class="company">{logo_html}{company}</div>
  </div>
  <div style="text-align: right;">
    <div class="invoice-title">INVOICE</div>
    <div style="font-size: 14px; color: #6b7280;">#{payment.id}</div>
  </div>
</div>

<table class="meta-table">
<tr><td class="meta-label">Bill To:</td><td>{client_name}</td></tr>
<tr><td class="meta-label">Email:</td><td>{client_email}</td></tr>
<tr><td class="meta-label">Date:</td><td>{pay_date}</td></tr>
<tr><td class="meta-label">Status:</td><td>{escape(payment.status)}</td></tr>
<tr><td class="meta-label">Payment Method:</td><td>{escape(payment.payment_method or "Card")}</td></tr>
</table>

<table class="items-table">
<thead>
<tr>
  <th>Description</th>
  <th class="amount-col">Amount</th>
</tr>
</thead>
<tbody>
<tr>
  <td>Payment #{payment.id}</td>
  <td class="amount-col">{escape(payment.currency)} {payment.amount}</td>
</tr>
</tbody>
<tfoot>
<tr class="total-row">
  <td>Total</td>
  <td class="amount-col">{escape(payment.currency)} {payment.amount}</td>
</tr>
</tfoot>
</table>

<div class="footer">
  <p>{company}</p>
  <p>{footer_text}</p>
</div>
</body>
</html>"""

        return html.encode("utf-8")

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
                    await self.send_payment_receipt(payment.id)
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
                await self.send_payment_receipt(payment.id)
            except (OSError, RuntimeError) as exc:
                logger.warning("Failed to send receipt for payment %s: %s", payment.id, exc)

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
                await self.send_payment_receipt(payment.id)
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

    async def sync_customer_from_id(self, customer_id: int) -> StripeCustomer:
        """Look up a local StripeCustomer by primary key.

        Raises ValueError if not found.
        """
        result = await self.db.execute(
            select(StripeCustomer).where(StripeCustomer.id == customer_id)
        )
        customer = result.scalar_one_or_none()
        if not customer:
            raise ValueError(f"Stripe customer {customer_id} not found")
        return customer

    async def create_and_send_invoice(
        self,
        customer_id: int,
        amount: float,
        description: str,
        user_id: int,
        currency: str = "USD",
        due_days: int = 30,
        quote_id: Optional[int] = None,
        payment_method_types: Optional[List[str]] = None,
    ) -> dict:
        """Create a Stripe Invoice, finalize it, and send it.

        Returns dict with invoice_id, payment_id, and status.
        Raises ValueError if Stripe is not configured or customer not found.
        """
        stripe = _get_stripe()
        if not stripe:
            raise ValueError("Stripe is not configured. Set STRIPE_SECRET_KEY environment variable.")

        customer = await self.sync_customer_from_id(customer_id)
        amount_cents = _to_cents(amount)

        # Create the draft Invoice FIRST (auto_advance=False so Stripe
        # doesn't finalize it behind our back), then attach a line item
        # pinned to that invoice. If anything after the Invoice.create
        # fails, the InvoiceItem is scoped to this invoice and gets
        # reaped when we void the draft — so it can't orphan-attach to
        # the customer's NEXT invoice (which was the silent double-
        # charge bug).
        invoice = None
        try:
            invoice_params = {
                "customer": customer.stripe_customer_id,
                "collection_method": "send_invoice",
                "days_until_due": due_days,
                "auto_advance": False,
            }
            if payment_method_types:
                invoice_params["payment_settings"] = {
                    "payment_method_types": payment_method_types,
                }
            idem_key = f"inv_{customer_id}_{uuid.uuid4().hex[:12]}"
            invoice = stripe.Invoice.create(
                **invoice_params,
                idempotency_key=idem_key,
            )

            stripe.InvoiceItem.create(
                customer=customer.stripe_customer_id,
                amount=amount_cents,
                currency=currency.lower(),
                description=description,
                invoice=invoice.id,
                idempotency_key=f"{idem_key}_item",
            )

            invoice = stripe.Invoice.finalize_invoice(invoice.id)
            invoice = stripe.Invoice.send_invoice(invoice.id)
        except Exception as exc:
            if invoice and hasattr(invoice, "id"):
                try:
                    stripe.Invoice.void_invoice(invoice.id)
                except Exception:
                    logger.warning("Failed to void draft invoice %s after error", invoice.id)
            raise ValueError(f"Failed to create invoice: {exc}") from exc

        payment = Payment(
            stripe_invoice_id=invoice.id,
            amount=amount,
            currency=currency.upper(),
            status="pending",
            customer_id=customer_id,
            quote_id=quote_id,
            owner_id=user_id,
            created_by_id=user_id,
        )
        self.db.add(payment)
        await self.db.flush()
        await self.db.refresh(payment)

        return {
            "invoice_id": invoice.id,
            "payment_id": payment.id,
            "status": "pending",
            "invoice_url": getattr(invoice, "hosted_invoice_url", None),
        }

    async def create_onboarding_link(
        self,
        success_url: str,
        cancel_url: str,
        contact_id: Optional[int] = None,
        company_id: Optional[int] = None,
    ) -> dict:
        """Create a Stripe customer portal / onboarding link.

        Returns dict with the URL. Raises ValueError if Stripe is not
        configured or neither contact_id nor company_id is provided.
        """
        if contact_id is None and company_id is None:
            raise ValueError("Either contact_id or company_id is required")

        stripe = _get_stripe()
        if not stripe:
            raise ValueError("Stripe is not configured. Set STRIPE_SECRET_KEY environment variable.")

        customer = await self.sync_customer(
            contact_id=contact_id,
            company_id=company_id,
        )

        session = stripe.checkout.Session.create(
            mode="setup",
            customer=customer.stripe_customer_id,
            success_url=success_url,
            cancel_url=cancel_url,
            idempotency_key=f"setup_{customer.id}_{uuid.uuid4().hex[:12]}",
        )

        return {"url": session.url}


class ProductService(CRUDService[Product, ProductCreate, ProductUpdate]):
    """Service for Product CRUD operations."""

    model = Product
    create_exclude_fields: set = set()
    update_exclude_fields: set = set()

    def _get_eager_load_options(self):
        return [selectinload(Product.prices)]

    async def get_list(
        self,
        page: int = 1,
        page_size: int = DEFAULT_PAGE_SIZE,
        is_active: Optional[bool] = None,
        owner_id: Optional[int] = None,
    ) -> Tuple[List[Product], int]:
        """Get paginated list of products."""
        query = select(Product).options(selectinload(Product.prices))

        if is_active is not None:
            query = query.where(Product.is_active == is_active)

        if owner_id:
            query = query.where(Product.owner_id == owner_id)

        count_query = select(func.count()).select_from(query.subquery())
        total_result = await self.db.execute(count_query)
        total = total_result.scalar() or 0

        offset = (page - 1) * page_size
        query = query.offset(offset).limit(page_size).order_by(Product.created_at.desc())

        result = await self.db.execute(query)
        products = list(result.scalars().all())

        return products, total


class StripeCustomerService:
    """Service for StripeCustomer operations."""

    def __init__(self, db):
        self.db = db

    async def get_by_id(self, id: int) -> Optional[StripeCustomer]:
        result = await self.db.execute(
            select(StripeCustomer).where(StripeCustomer.id == id)
        )
        return result.scalar_one_or_none()

    async def get_list(
        self,
        page: int = 1,
        page_size: int = DEFAULT_PAGE_SIZE,
    ) -> Tuple[List[StripeCustomer], int]:
        """Get paginated list of Stripe customers."""
        query = select(StripeCustomer)

        count_query = select(func.count()).select_from(query.subquery())
        total_result = await self.db.execute(count_query)
        total = total_result.scalar() or 0

        offset = (page - 1) * page_size
        query = query.offset(offset).limit(page_size).order_by(
            StripeCustomer.created_at.desc()
        )

        result = await self.db.execute(query)
        customers = list(result.scalars().all())

        return customers, total


class SubscriptionService:
    """Service for Subscription operations."""

    def __init__(self, db):
        self.db = db

    async def get_by_id(self, id: int) -> Optional[Subscription]:
        result = await self.db.execute(
            select(Subscription)
            .options(
                selectinload(Subscription.customer),
                selectinload(Subscription.price),
            )
            .where(Subscription.id == id)
        )
        return result.scalar_one_or_none()

    async def get_list(
        self,
        page: int = 1,
        page_size: int = DEFAULT_PAGE_SIZE,
        status: Optional[str] = None,
        customer_id: Optional[int] = None,
        owner_id: Optional[int] = None,
    ) -> Tuple[List[Subscription], int]:
        """Get paginated list of subscriptions."""
        query = select(Subscription).options(
            selectinload(Subscription.customer),
            selectinload(Subscription.price),
        )

        if status:
            query = query.where(Subscription.status == status)

        if customer_id:
            query = query.where(Subscription.customer_id == customer_id)

        if owner_id:
            query = query.where(Subscription.owner_id == owner_id)

        count_query = select(func.count()).select_from(query.subquery())
        total_result = await self.db.execute(count_query)
        total = total_result.scalar() or 0

        offset = (page - 1) * page_size
        query = query.offset(offset).limit(page_size).order_by(
            Subscription.created_at.desc()
        )

        result = await self.db.execute(query)
        subscriptions = list(result.scalars().all())

        return subscriptions, total

    async def cancel(self, subscription: Subscription) -> Subscription:
        """Cancel a subscription.

        If Stripe is configured, cancels on Stripe.
        Otherwise marks the local record as canceled.
        """
        stripe = _get_stripe()
        if stripe and subscription.stripe_subscription_id and not subscription.stripe_subscription_id.startswith("local_"):
            try:
                stripe.Subscription.modify(
                    subscription.stripe_subscription_id,
                    cancel_at_period_end=True,
                )
            except Exception as exc:
                logger.warning("Failed to cancel subscription on Stripe %s: %s", subscription.stripe_subscription_id, exc)

        subscription.status = "canceled"
        subscription.cancel_at_period_end = True
        await self.db.flush()
        await self.db.refresh(subscription)
        return subscription
