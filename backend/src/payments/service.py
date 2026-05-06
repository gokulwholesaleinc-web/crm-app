"""Payment service layer."""

import hashlib
import logging
import uuid
from collections.abc import Sequence
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import String, func, or_, select
from sqlalchemy.orm import selectinload

from src.config import settings
from src.core.base_service import CRUDService
from src.core.constants import DEFAULT_PAGE_SIZE
from src.payments.exceptions import NoRecipientEmailError
from src.payments.models import (
    Payment,
    Product,
    StripeCustomer,
    Subscription,
)
from src.payments.schemas import (
    PaymentCreate,
    PaymentUpdate,
    ProductCreate,
    ProductUpdate,
)
from src.payments.webhook_processor import WebhookProcessor


# Common: rounding money to integer cents. Stripe expects amounts as ints.
# Use banker's-rounding-free half-up so $19.995 → 2000¢, not 1999¢.
def _to_cents(amount: float | int | Decimal | str) -> int:
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
        import stripe  # pyright: ignore[reportMissingImports]
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

    async def attach_proposals(self, payments: list[Payment]) -> None:
        """Look up Proposals matching each payment's Stripe identifiers and
        stuff them onto the SQLAlchemy instance as `.proposal` so PaymentResponse
        (which uses `from_attributes=True`) serializes them. Proposals don't
        carry a payment_id FK; the only link is shared Stripe artifact IDs.
        """
        if not payments:
            return

        from src.proposals.models import Proposal

        invoice_ids = {p.stripe_invoice_id for p in payments if p.stripe_invoice_id}
        checkout_ids = {p.stripe_checkout_session_id for p in payments if p.stripe_checkout_session_id}
        if not invoice_ids and not checkout_ids:
            for p in payments:
                p.proposal = None  # type: ignore[attr-defined]
            return

        clauses = []
        if invoice_ids:
            clauses.append(Proposal.stripe_invoice_id.in_(invoice_ids))
        if checkout_ids:
            clauses.append(Proposal.stripe_checkout_session_id.in_(checkout_ids))
        result = await self.db.execute(select(Proposal).where(or_(*clauses)))
        proposals = list(result.scalars().all())
        by_invoice = {pr.stripe_invoice_id: pr for pr in proposals if pr.stripe_invoice_id}
        by_checkout = {pr.stripe_checkout_session_id: pr for pr in proposals if pr.stripe_checkout_session_id}
        for p in payments:
            match = None
            if p.stripe_invoice_id:
                match = by_invoice.get(p.stripe_invoice_id)
            if not match and p.stripe_checkout_session_id:
                match = by_checkout.get(p.stripe_checkout_session_id)
            p.proposal = match  # type: ignore[attr-defined]

    async def get_list(
        self,
        page: int = 1,
        page_size: int = DEFAULT_PAGE_SIZE,
        status: str | None = None,
        customer_id: int | None = None,
        contact_id: int | None = None,
        company_id: int | None = None,
        owner_id: int | None = None,
        shared_entity_ids: list[int] | None = None,
        search: str | None = None,
    ) -> tuple[list[Payment], int]:
        """Get paginated list of payments with filters.

        ``contact_id`` and ``company_id`` filter by the CRM relationship on
        StripeCustomer — the contact/company detail page uses these to show
        every payment, invoice, and checkout session for that record.
        """
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

        # The contact/company/search filters all need StripeCustomer columns;
        # join once so we don't end up with duplicated joins or ambiguous aliases.
        needs_customer_join = (
            contact_id is not None or company_id is not None or bool(search)
        )
        if needs_customer_join:
            query = query.join(Payment.customer, isouter=True)

        if contact_id is not None:
            query = query.where(StripeCustomer.contact_id == contact_id)
        if company_id is not None:
            query = query.where(StripeCustomer.company_id == company_id)

        if owner_id:
            if shared_entity_ids:
                query = query.where(
                    or_(Payment.owner_id == owner_id, Payment.id.in_(shared_entity_ids))
                )
            else:
                query = query.where(Payment.owner_id == owner_id)

        if search:
            search_term = f"%{search}%"
            query = query.where(
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
        amount: float | Decimal,
        currency: str,
        success_url: str,
        cancel_url: str,
        user_id: int,
        customer_id: int | None = None,
        quote_id: int | None = None,
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
        amount: float | Decimal,
        currency: str,
        user_id: int,
        customer_id: int | None = None,
        opportunity_id: int | None = None,
        quote_id: int | None = None,
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
        contact_id: int | None = None,
        company_id: int | None = None,
        email: str | None = None,
        name: str | None = None,
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

    async def process_webhook(self, payload: bytes, sig_header: str) -> dict:
        """Process a Stripe webhook event.

        Delegates to WebhookProcessor for all verification and dispatching.
        Kept here for backward compatibility with the router and existing tests.
        """
        processor = WebhookProcessor(self.db)
        return await processor.process_webhook(payload, sig_header)

    @staticmethod
    def _verify_webhook_signature(
        payload: bytes,
        sig_header: str,
        secret: str,
        tolerance: int = 300,
    ) -> bool:
        """Verify Stripe webhook HMAC-SHA256 signature with timestamp tolerance.

        Delegates to WebhookProcessor. Kept here for backward compatibility
        with existing tests that call PaymentService._verify_webhook_signature.
        """
        return WebhookProcessor._verify_webhook_signature(
            payload, sig_header, secret, tolerance=tolerance
        )

    async def send_payment_receipt(self, payment_id: int) -> None:
        """Send branded receipt email after successful payment.

        Raises ``ValueError`` when the payment has no customer or the
        customer has no email on file — webhook callers catch and log
        (matching the pattern already in `_handle_payment_succeeded`),
        and the staff "Resend Receipt" router surfaces the message via
        a 400 so the user knows why the email didn't go out.
        """
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
            raise ValueError(f"Payment {payment_id} not found")

        to_email = payment.customer.email if payment.customer else None
        if not to_email:
            raise NoRecipientEmailError(
                "Customer has no email on file — add an email address "
                "and try again",
            )
        client_name = (payment.customer.name if payment.customer else None) or "Customer"

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

        Delegates to payments.pdf module for the HTML rendering.
        """
        from src.payments.pdf import generate_invoice_pdf as _gen
        return await _gen(self.db, payment_id)

    async def send_payment_invoice(self, payment_id: int) -> None:
        """Email the invoice to the customer with the rendered PDF attached.

        Used by the staff "Resend Invoice" button when the customer reports
        not receiving the original. Reuses the same PDF generator as the
        download endpoint plus a dedicated branded email template.
        """
        from src.email.branded_templates import (
            TenantBrandingHelper,
            render_payment_invoice_email,
        )
        from src.email.service import EmailService
        from src.email.types import EmailAttachment

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
            raise ValueError(f"Payment {payment_id} not found")

        to_email = payment.customer.email if payment.customer else None
        if not to_email:
            raise ValueError("Customer has no email on file")

        client_name = (payment.customer.name if payment.customer else None) or "Customer"

        branding = TenantBrandingHelper.get_default_branding()
        if payment.owner_id:
            branding = await TenantBrandingHelper.get_branding_for_user(
                self.db, payment.owner_id
            )

        invoice_data = {
            "invoice_number": str(payment.id),
            "client_name": client_name,
            "amount": str(payment.amount),
            "currency": payment.currency,
            "due_date": payment.created_at.strftime("%Y-%m-%d") if payment.created_at else "",
            "payment_url": payment.stripe_payment_url or "",
        }

        subject, html_body = render_payment_invoice_email(branding, invoice_data)

        # generate_invoice_pdf today returns HTML bytes (the WeasyPrint
        # fallback path); attach with the appropriate content-type so
        # mail clients render or download as expected.
        pdf_bytes = await self.generate_invoice_pdf(payment_id)
        attachment: EmailAttachment = {
            "filename": f"invoice-{payment_id}.html",
            "content": pdf_bytes,
            "content_type": "text/html",
        }

        email_service = EmailService(self.db)
        await email_service.queue_email(
            to_email=to_email,
            subject=subject,
            body=html_body,
            sent_by_id=payment.owner_id,
            entity_type="payments",
            entity_id=payment.id,
            attachments=[attachment],
        )

    async def _handle_checkout_completed(self, session_obj: dict) -> None:
        """Handle checkout.session.completed event. Delegates to WebhookProcessor."""
        processor = WebhookProcessor(self.db)
        return await processor._handle_checkout_completed(session_obj)

    async def _handle_payment_succeeded(self, intent_obj: dict) -> None:
        """Handle payment_intent.succeeded event. Delegates to WebhookProcessor."""
        processor = WebhookProcessor(self.db)
        return await processor._handle_payment_succeeded(intent_obj)

    async def _find_payment(self, lookup_field, obj: dict, obj_key: str = "id") -> Payment | None:
        """Look up a Payment by a Stripe ID field. Delegates to WebhookProcessor."""
        processor = WebhookProcessor(self.db)
        return await processor._find_payment(lookup_field, obj, obj_key=obj_key)

    async def _set_payment_status(
        self, payment: Payment | None, new_status: str,
        guard_statuses: tuple = ("succeeded", "refunded"),
    ) -> None:
        """Set payment status. Delegates to WebhookProcessor."""
        processor = WebhookProcessor(self.db)
        return await processor._set_payment_status(payment, new_status, guard_statuses=guard_statuses)

    async def _handle_payment_failed(self, intent_obj: dict) -> None:
        """Handle payment_intent.payment_failed event. Delegates to WebhookProcessor."""
        processor = WebhookProcessor(self.db)
        return await processor._handle_payment_failed(intent_obj)

    async def _handle_charge_refunded(self, charge_obj: dict) -> None:
        """Handle charge.refunded event. Delegates to WebhookProcessor."""
        processor = WebhookProcessor(self.db)
        return await processor._handle_charge_refunded(charge_obj)

    async def _handle_subscription_created(self, sub_obj: dict) -> None:
        """Handle customer.subscription.created. Delegates to WebhookProcessor."""
        processor = WebhookProcessor(self.db)
        return await processor._handle_subscription_created(sub_obj)

    async def _handle_subscription_updated(self, sub_obj: dict) -> None:
        """Handle customer.subscription.updated. Delegates to WebhookProcessor."""
        processor = WebhookProcessor(self.db)
        return await processor._handle_subscription_updated(sub_obj)

    async def _handle_subscription_deleted(self, sub_obj: dict) -> None:
        """Handle subscription deleted event. Delegates to WebhookProcessor."""
        processor = WebhookProcessor(self.db)
        return await processor._handle_subscription_deleted(sub_obj)

    async def _handle_invoice_paid(self, invoice_obj: dict) -> None:
        """Handle invoice.paid. Delegates to WebhookProcessor."""
        processor = WebhookProcessor(self.db)
        return await processor._handle_invoice_paid(invoice_obj)

    async def _handle_invoice_payment_failed(self, invoice_obj: dict) -> None:
        """Handle invoice.payment_failed event. Delegates to WebhookProcessor."""
        processor = WebhookProcessor(self.db)
        return await processor._handle_invoice_payment_failed(invoice_obj)

    async def _handle_invoice_sent(self, invoice_obj: dict) -> None:
        """Handle invoice.sent event. Delegates to WebhookProcessor."""
        processor = WebhookProcessor(self.db)
        return await processor._handle_invoice_sent(invoice_obj)

    async def _handle_async_payment_succeeded(self, session_obj: dict) -> None:
        """Handle checkout.session.async_payment_succeeded (ACH success). Delegates to WebhookProcessor."""
        processor = WebhookProcessor(self.db)
        return await processor._handle_async_payment_succeeded(session_obj)

    async def _handle_async_payment_failed(self, session_obj: dict) -> None:
        """Handle checkout.session.async_payment_failed (ACH failure). Delegates to WebhookProcessor."""
        processor = WebhookProcessor(self.db)
        return await processor._handle_async_payment_failed(session_obj)

    async def _handle_setup_intent_succeeded(self, setup_obj: dict) -> None:
        """Handle setup_intent.succeeded. Delegates to WebhookProcessor."""
        processor = WebhookProcessor(self.db)
        return await processor._handle_setup_intent_succeeded(setup_obj)

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

    def _stripe_create_finalize_send_invoice(
        self,
        *,
        stripe,  # the stripe module
        stripe_customer_id: str,
        amount: float | Decimal,
        currency: str,
        description: str,
        due_days: int,
        idem_base: str,
        metadata: dict | None = None,
        payment_method_types: Sequence[str] | None = None,
    ):
        """Create+finalize+send a Stripe Invoice with a single line item.

        Shared between ``create_and_send_invoice`` (quote path) and
        ``create_invoice_for_proposal`` (proposal path). Both flows
        follow the same idempotent Invoice.create → InvoiceItem.create →
        finalize → send sequence, and both need to void the draft if
        anything mid-flight fails so the orphan InvoiceItem can't
        silently attach to the customer's next invoice.

        Returns the finalized Stripe Invoice object. Raises ValueError
        on any Stripe failure (having already attempted a void).
        """
        invoice = None
        try:
            invoice_params: dict = {
                "customer": stripe_customer_id,
                "collection_method": "send_invoice",
                "days_until_due": due_days,
                "auto_advance": False,
            }
            if metadata:
                invoice_params["metadata"] = metadata
            if payment_method_types:
                invoice_params["payment_settings"] = {
                    "payment_method_types": payment_method_types,
                }

            invoice = stripe.Invoice.create(
                **invoice_params,
                idempotency_key=idem_base,
            )
            if not invoice.id:
                raise ValueError("Stripe returned an invoice without an id")

            stripe.InvoiceItem.create(
                customer=stripe_customer_id,
                amount=_to_cents(amount),
                currency=currency.lower(),
                description=description,
                invoice=invoice.id,
                idempotency_key=f"{idem_base}_item",
            )
            invoice = stripe.Invoice.finalize_invoice(invoice.id)
            return stripe.Invoice.send_invoice(invoice.id)
        except Exception as exc:
            if invoice and invoice.id:
                try:
                    stripe.Invoice.void_invoice(invoice.id)
                except Exception:
                    logger.warning(
                        "Failed to void draft invoice %s after error", invoice.id,
                    )
            raise ValueError(f"Failed to create invoice: {exc}") from exc

    async def create_and_send_invoice(
        self,
        customer_id: int,
        amount: float | Decimal,
        description: str,
        user_id: int,
        currency: str = "USD",
        due_days: int = 30,
        quote_id: int | None = None,
        payment_method_types: Sequence[str] | None = None,
    ) -> dict:
        """Create a Stripe Invoice, finalize it, and send it.

        Returns dict with invoice_id, payment_id, and status.
        Raises ValueError if Stripe is not configured or customer not found.
        """
        stripe = _get_stripe()
        if not stripe:
            raise ValueError("Stripe is not configured. Set STRIPE_SECRET_KEY environment variable.")

        customer = await self.sync_customer_from_id(customer_id)
        invoice = self._stripe_create_finalize_send_invoice(
            stripe=stripe,
            stripe_customer_id=customer.stripe_customer_id,
            amount=amount,
            currency=currency,
            description=description,
            due_days=due_days,
            idem_base=f"inv_{customer_id}_{uuid.uuid4().hex[:12]}",
            payment_method_types=payment_method_types,
        )

        invoice_url = getattr(invoice, "hosted_invoice_url", None)
        payment = Payment(
            stripe_invoice_id=invoice.id,
            stripe_payment_url=invoice_url,
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
            "invoice_url": invoice_url,
        }

    async def create_invoice_for_proposal(
        self,
        *,
        proposal_id: int,
        contact_id: int | None,
        company_id: int | None,
        amount: Decimal,
        currency: str,
        description: str,
        owner_id: int | None,
        due_days: int = 30,
    ) -> dict:
        """Create+finalize+send a Stripe Invoice for an accepted one-time proposal.

        Returns ``{stripe_invoice_id, stripe_payment_url, payment_id}``.

        Tags the Stripe invoice with ``metadata.proposal_id`` so the
        webhook can match the invoice.paid event back to the CRM
        proposal without a local-side join.

        Raises ValueError when Stripe is not configured or neither
        contact_id nor company_id is supplied.
        """
        if contact_id is None and company_id is None:
            raise ValueError("proposal must link to a contact or company")

        stripe = _get_stripe()
        if not stripe:
            raise ValueError("Stripe is not configured")

        customer = await self.sync_customer(
            contact_id=contact_id,
            company_id=company_id,
        )
        if not customer.stripe_customer_id:
            raise ValueError(
                "Stripe customer was not created — check Stripe connectivity",
            )

        # Deterministic idempotency key — if this method is ever called
        # twice for the same proposal (transient retry, race the row lock
        # missed, etc.) Stripe returns the original invoice instead of
        # creating a second charge. The proposal_id is the logical
        # operation identifier; bump the suffix when we intentionally
        # change the invoice shape (e.g. moving to multi-line items).
        invoice = self._stripe_create_finalize_send_invoice(
            stripe=stripe,
            stripe_customer_id=customer.stripe_customer_id,
            amount=amount,
            currency=currency,
            description=description,
            due_days=due_days,
            idem_base=f"proposal_{proposal_id}_invoice_v1",
            metadata={"proposal_id": str(proposal_id)},
        )

        invoice_url = getattr(invoice, "hosted_invoice_url", None)
        payment = Payment(
            stripe_invoice_id=invoice.id,
            stripe_payment_url=invoice_url,
            amount=amount,
            currency=currency.upper(),
            status="pending",
            customer_id=customer.id,
            owner_id=owner_id,
            created_by_id=owner_id,
        )
        self.db.add(payment)
        await self.db.flush()
        await self.db.refresh(payment)

        return {
            "stripe_invoice_id": invoice.id,
            "stripe_payment_url": invoice_url,
            "payment_id": payment.id,
        }

    async def create_and_send_subscription_checkout(
        self,
        *,
        customer_id: int,
        amount: Decimal,
        description: str,
        user_id: int,
        currency: str,
        interval: str,
        interval_count: int,
        success_url: str,
        cancel_url: str,
    ) -> dict:
        """Create a subscription Checkout Session for an existing StripeCustomer.

        Returns ``{checkout_session_id, checkout_url, payment_id}``.
        """
        if amount <= 0:
            raise ValueError("amount must be > 0")
        if interval_count < 1:
            raise ValueError("interval_count must be >= 1")

        stripe = _get_stripe()
        if not stripe:
            raise ValueError("Stripe is not configured")

        customer = await self.sync_customer_from_id(customer_id)
        if not customer.stripe_customer_id:
            raise ValueError(
                "Stripe customer was not created — check Stripe connectivity",
            )

        # Stable key over the logical request shape so a network retry
        # collapses to one Session. Includes success_url + cancel_url so
        # changing the redirect target spawns a fresh Session instead of
        # silently returning the cached one with the old URLs.
        idem_payload = (
            f"{customer_id}|{user_id}|{int(_to_cents(amount))}|{currency.lower()}"
            f"|{interval}|{interval_count}|{description}|{success_url}|{cancel_url}"
        )
        idempotency_key = f"sub_chk_{hashlib.sha256(idem_payload.encode()).hexdigest()[:24]}"

        session = stripe.checkout.Session.create(
            mode="subscription",
            customer=customer.stripe_customer_id,
            success_url=success_url,
            cancel_url=cancel_url,
            line_items=[
                {
                    "quantity": 1,
                    "price_data": {
                        "currency": currency.lower(),
                        "unit_amount": _to_cents(amount),
                        "recurring": {
                            "interval": interval,
                            "interval_count": interval_count,
                        },
                        "product_data": {"name": description},
                    },
                },
            ],
            idempotency_key=idempotency_key,
        )

        payment = Payment(
            stripe_checkout_session_id=session.id,
            stripe_payment_url=session.url,
            amount=amount,
            currency=currency.upper(),
            status="pending",
            customer_id=customer_id,
            owner_id=user_id,
            created_by_id=user_id,
        )
        self.db.add(payment)
        await self.db.flush()
        await self.db.refresh(payment)

        return {
            "checkout_session_id": session.id,
            "checkout_url": session.url,
            "payment_id": payment.id,
        }

    async def create_subscription_checkout_for_proposal(
        self,
        *,
        proposal_id: int,
        contact_id: int | None,
        company_id: int | None,
        amount: Decimal,
        currency: str,
        description: str,
        interval: str,
        interval_count: int,
        success_url: str,
        cancel_url: str,
        idempotency_key: str | None = None,
    ) -> dict:
        """Create a Stripe Checkout Session (mode=subscription) for an accepted
        subscription proposal.

        Uses Stripe's inline ``price_data`` so we don't have to pre-create
        a Product + Price for every proposal. The client completes the
        checkout flow, which collects payment method + charges the first
        period, and Stripe sends us ``checkout.session.completed`` with
        the resulting subscription id.

        ``metadata.proposal_id`` carries on both the session and the
        underlying subscription, so the webhook can reconcile.

        Returns ``{stripe_checkout_session_id, stripe_payment_url}``.
        """
        if contact_id is None and company_id is None:
            raise ValueError("proposal must link to a contact or company")
        if interval not in ("month", "year"):
            raise ValueError("interval must be 'month' or 'year'")
        if interval_count < 1:
            raise ValueError("interval_count must be >= 1")

        stripe = _get_stripe()
        if not stripe:
            raise ValueError("Stripe is not configured")

        customer = await self.sync_customer(
            contact_id=contact_id,
            company_id=company_id,
        )
        if not customer.stripe_customer_id:
            raise ValueError(
                "Stripe customer was not created — check Stripe connectivity",
            )

        session = stripe.checkout.Session.create(
            mode="subscription",
            customer=customer.stripe_customer_id,
            success_url=success_url,
            cancel_url=cancel_url,
            line_items=[
                {
                    "quantity": 1,
                    "price_data": {
                        "currency": currency.lower(),
                        "unit_amount": _to_cents(amount),
                        "recurring": {
                            "interval": interval,
                            "interval_count": interval_count,
                        },
                        "product_data": {"name": description},
                    },
                },
            ],
            metadata={"proposal_id": str(proposal_id)},
            subscription_data={"metadata": {"proposal_id": str(proposal_id)}},
            # Deterministic key — same reasoning as create_invoice_for_proposal.
            # Callers regenerating an expired session must pass a distinct key
            # so Stripe doesn't return the (still-cached) original.
            idempotency_key=idempotency_key or f"proposal_sub_{proposal_id}_v1",
        )

        return {
            "stripe_checkout_session_id": session.id,
            "stripe_payment_url": session.url,
        }

    async def create_onboarding_link(
        self,
        success_url: str,
        cancel_url: str,
        contact_id: int | None = None,
        company_id: int | None = None,
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
        is_active: bool | None = None,
        owner_id: int | None = None,
    ) -> tuple[list[Product], int]:
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

    async def get_by_id(self, id: int) -> StripeCustomer | None:
        result = await self.db.execute(
            select(StripeCustomer).where(StripeCustomer.id == id)
        )
        return result.scalar_one_or_none()

    async def get_list(
        self,
        page: int = 1,
        page_size: int = DEFAULT_PAGE_SIZE,
    ) -> tuple[list[StripeCustomer], int]:
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

    async def get_by_id(self, id: int) -> Subscription | None:
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
        status: str | None = None,
        customer_id: int | None = None,
        contact_id: int | None = None,
        company_id: int | None = None,
        owner_id: int | None = None,
    ) -> tuple[list[Subscription], int]:
        """Get paginated list of subscriptions.

        ``contact_id`` and ``company_id`` filter by the CRM relationship on
        StripeCustomer so the contact/company detail page can show all
        recurring billing for that record alongside one-time payments.
        """
        query = select(Subscription).options(
            selectinload(Subscription.customer),
            selectinload(Subscription.price),
        )

        if status:
            query = query.where(Subscription.status == status)

        if customer_id:
            query = query.where(Subscription.customer_id == customer_id)

        if contact_id is not None or company_id is not None:
            query = query.join(Subscription.customer)
            if contact_id is not None:
                query = query.where(StripeCustomer.contact_id == contact_id)
            if company_id is not None:
                query = query.where(StripeCustomer.company_id == company_id)

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
