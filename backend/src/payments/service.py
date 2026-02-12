"""Payment service layer."""

import hashlib
import hmac
import json
import logging
from typing import Optional, List, Tuple

from sqlalchemy import select, func, or_
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
from src.core.base_service import CRUDService
from src.core.constants import DEFAULT_PAGE_SIZE
from src.config import settings

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

        count_query = select(func.count()).select_from(query.subquery())
        total_result = await self.db.execute(count_query)
        total = total_result.scalar() or 0

        offset = (page - 1) * page_size
        query = query.offset(offset).limit(page_size).order_by(Payment.created_at.desc())

        result = await self.db.execute(query)
        payments = list(result.scalars().all())

        return payments, total

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

        # Create Stripe checkout session
        session = stripe.checkout.Session.create(
            payment_method_types=["card"],
            line_items=[{
                "price_data": {
                    "currency": currency.lower(),
                    "product_data": {"name": f"Payment - {currency} {amount}"},
                    "unit_amount": int(amount * 100),
                },
                "quantity": 1,
            }],
            mode="payment",
            success_url=success_url,
            cancel_url=cancel_url,
            customer=stripe_customer_id,
        )

        # Create local payment record
        payment = Payment(
            stripe_checkout_session_id=session.id,
            amount=amount,
            currency=currency,
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
            "amount": int(amount * 100),
            "currency": currency.lower(),
        }
        if stripe_customer_id:
            intent_params["customer"] = stripe_customer_id

        intent = stripe.PaymentIntent.create(**intent_params)

        # Create local payment record
        payment = Payment(
            stripe_payment_intent_id=intent.id,
            amount=amount,
            currency=currency,
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
            # Generate a local placeholder ID when Stripe is not configured
            import uuid
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

        Verifies the webhook signature using HMAC-SHA256 and processes
        the event idempotently.

        Returns dict with event type and processing result.
        Raises ValueError on invalid signature or missing config.
        """
        webhook_secret = getattr(settings, "STRIPE_WEBHOOK_SECRET", "")
        if not webhook_secret:
            raise ValueError("Stripe webhook secret is not configured.")

        # Verify HMAC-SHA256 signature
        if not self._verify_webhook_signature(payload, sig_header, webhook_secret):
            raise ValueError("Invalid webhook signature.")

        event_data = json.loads(payload)
        event_type = event_data.get("type", "")
        event_id = event_data.get("id", "")

        # Idempotency check: see if we already processed this event
        # We use the payment_intent_id or checkout_session_id to check
        obj = event_data.get("data", {}).get("object", {})

        if event_type == "checkout.session.completed":
            await self._handle_checkout_completed(obj)
        elif event_type == "payment_intent.succeeded":
            await self._handle_payment_succeeded(obj)
        elif event_type == "payment_intent.payment_failed":
            await self._handle_payment_failed(obj)
        elif event_type == "charge.refunded":
            await self._handle_charge_refunded(obj)
        elif event_type in ("customer.subscription.created", "customer.subscription.updated"):
            await self._handle_subscription_updated(obj)
        elif event_type == "customer.subscription.deleted":
            await self._handle_subscription_deleted(obj)

        return {"event_type": event_type, "event_id": event_id, "status": "processed"}

    @staticmethod
    def _verify_webhook_signature(payload: bytes, sig_header: str, secret: str) -> bool:
        """Verify Stripe webhook HMAC-SHA256 signature.

        Stripe sends the signature in the format:
        t=<timestamp>,v1=<signature>
        """
        try:
            elements = dict(
                pair.split("=", 1) for pair in sig_header.split(",") if "=" in pair
            )
            timestamp = elements.get("t", "")
            signature = elements.get("v1", "")

            if not timestamp or not signature:
                return False

            # Compute expected signature
            signed_payload = f"{timestamp}.".encode() + payload
            expected = hmac.new(
                secret.encode(), signed_payload, hashlib.sha256
            ).hexdigest()

            return hmac.compare_digest(expected, signature)
        except Exception:
            return False

    async def _handle_checkout_completed(self, session_obj: dict) -> None:
        """Handle checkout.session.completed event."""
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
            # Extract receipt URL from charges if available
            charges = intent_obj.get("charges", {}).get("data", [])
            if charges:
                payment.receipt_url = charges[0].get("receipt_url")
                payment.payment_method = charges[0].get("payment_method_details", {}).get("type")
            await self.db.flush()

    async def _handle_payment_failed(self, intent_obj: dict) -> None:
        """Handle payment_intent.payment_failed event."""
        intent_id = intent_obj.get("id")
        if not intent_id:
            return

        result = await self.db.execute(
            select(Payment).where(Payment.stripe_payment_intent_id == intent_id)
        )
        payment = result.scalar_one_or_none()
        if payment and payment.status not in ("succeeded", "refunded"):
            payment.status = "failed"
            await self.db.flush()

    async def _handle_charge_refunded(self, charge_obj: dict) -> None:
        """Handle charge.refunded event."""
        payment_intent_id = charge_obj.get("payment_intent")
        if not payment_intent_id:
            return

        result = await self.db.execute(
            select(Payment).where(Payment.stripe_payment_intent_id == payment_intent_id)
        )
        payment = result.scalar_one_or_none()
        if payment:
            payment.status = "refunded"
            await self.db.flush()

    async def _handle_subscription_updated(self, sub_obj: dict) -> None:
        """Handle subscription created/updated events."""
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
