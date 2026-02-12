"""Quote service layer."""

import os
from datetime import datetime, timezone
from typing import Optional, List, Tuple
from sqlalchemy import select, func, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from src.quotes.models import Quote, QuoteLineItem, QuoteTemplate, ProductBundle, ProductBundleItem
from src.quotes.schemas import (
    QuoteCreate, QuoteUpdate, QuoteLineItemCreate,
    ProductBundleCreate, ProductBundleUpdate,
)
from src.core.base_service import CRUDService, StatusTransitionMixin, BaseService
from src.core.constants import DEFAULT_PAGE_SIZE
from src.core.filtering import build_token_search
from src.email.branded_templates import TenantBrandingHelper, render_quote_email
from src.email.pdf_service import BrandedPDFGenerator
from src.email.service import EmailService

# Valid status transitions
VALID_TRANSITIONS = {
    "draft": ["sent"],
    "sent": ["viewed", "accepted", "rejected"],
    "viewed": ["accepted", "rejected"],
    "accepted": [],
    "rejected": [],
    "expired": [],
}


class QuoteService(StatusTransitionMixin, CRUDService[Quote, QuoteCreate, QuoteUpdate]):
    """Service for Quote CRUD operations."""

    model = Quote
    create_exclude_fields = {"line_items"}
    update_exclude_fields = set()

    def _get_eager_load_options(self):
        return [
            selectinload(Quote.line_items),
            selectinload(Quote.opportunity),
            selectinload(Quote.contact),
            selectinload(Quote.company),
        ]

    async def _generate_quote_number(self) -> str:
        """Generate auto-incrementing quote number: QT-{year}-{seq}."""
        year = datetime.now(timezone.utc).year
        prefix = f"QT-{year}-"

        result = await self.db.execute(
            select(func.count(Quote.id)).where(
                Quote.quote_number.like(f"{prefix}%")
            )
        )
        count = result.scalar() or 0
        seq = count + 1
        return f"{prefix}{seq:04d}"

    def _calculate_line_item_total(self, item: QuoteLineItem) -> float:
        """Calculate total for a single line item."""
        return float(item.quantity * item.unit_price) - float(item.discount)

    def _recalculate_totals(self, quote: Quote) -> None:
        """Recalculate subtotal, tax_amount, and total from line items and discount."""
        subtotal = float(sum(
            self._calculate_line_item_total(item) for item in quote.line_items
        ))
        quote.subtotal = subtotal

        # Apply quote-level discount
        discount_amount = 0.0
        if quote.discount_type == "percent" and quote.discount_value:
            discount_amount = subtotal * (float(quote.discount_value) / 100)
        elif quote.discount_type == "fixed" and quote.discount_value:
            discount_amount = float(quote.discount_value)

        after_discount = subtotal - discount_amount

        # Apply tax
        tax_rate = float(quote.tax_rate) if quote.tax_rate else 0.0
        quote.tax_amount = after_discount * (tax_rate / 100) if tax_rate else 0
        quote.total = after_discount + float(quote.tax_amount)

    async def get_list(
        self,
        page: int = 1,
        page_size: int = DEFAULT_PAGE_SIZE,
        search: Optional[str] = None,
        status: Optional[str] = None,
        contact_id: Optional[int] = None,
        company_id: Optional[int] = None,
        opportunity_id: Optional[int] = None,
        owner_id: Optional[int] = None,
        shared_entity_ids: Optional[List[int]] = None,
    ) -> Tuple[List[Quote], int]:
        """Get paginated list of quotes with filters."""
        query = (
            select(Quote)
            .options(
                selectinload(Quote.line_items),
                selectinload(Quote.opportunity),
                selectinload(Quote.contact),
                selectinload(Quote.company),
            )
        )

        if search:
            search_condition = build_token_search(search, Quote.title, Quote.quote_number)
            if search_condition is not None:
                query = query.where(search_condition)

        if status:
            query = query.where(Quote.status == status)

        if contact_id:
            query = query.where(Quote.contact_id == contact_id)

        if company_id:
            query = query.where(Quote.company_id == company_id)

        if opportunity_id:
            query = query.where(Quote.opportunity_id == opportunity_id)

        if owner_id:
            if shared_entity_ids:
                query = query.where(
                    or_(Quote.owner_id == owner_id, Quote.id.in_(shared_entity_ids))
                )
            else:
                query = query.where(Quote.owner_id == owner_id)

        count_query = select(func.count()).select_from(query.subquery())
        total_result = await self.db.execute(count_query)
        total = total_result.scalar()

        offset = (page - 1) * page_size
        query = query.offset(offset).limit(page_size).order_by(Quote.created_at.desc())

        result = await self.db.execute(query)
        quotes = list(result.scalars().all())

        return quotes, total

    async def create(self, data: QuoteCreate, user_id: int) -> Quote:
        """Create a new quote with optional line items."""
        quote_number = await self._generate_quote_number()

        # Extract line items before creating quote
        line_items_data = data.line_items or []

        # Create quote without line_items field
        quote_data = data.model_dump(exclude={"line_items"})
        quote_data["quote_number"] = quote_number
        quote_data["created_by_id"] = user_id

        quote = Quote(**quote_data)
        self.db.add(quote)
        await self.db.flush()

        # Add line items
        for item_data in line_items_data:
            item = QuoteLineItem(
                quote_id=quote.id,
                description=item_data.description,
                quantity=item_data.quantity,
                unit_price=item_data.unit_price,
                discount=item_data.discount,
                sort_order=item_data.sort_order,
            )
            item.total = self._calculate_line_item_total(item)
            self.db.add(item)

        await self.db.flush()
        await self.db.refresh(quote)

        # Recalculate totals
        self._recalculate_totals(quote)
        await self.db.flush()
        await self.db.refresh(quote)

        return quote

    async def update(self, instance: Quote, data: QuoteUpdate, user_id: int) -> Quote:
        """Update a quote."""
        quote = await super().update(instance, data, user_id)

        # Recalculate totals if relevant fields changed
        self._recalculate_totals(quote)
        await self.db.flush()
        await self.db.refresh(quote)

        return quote

    async def add_line_item(self, quote: Quote, data: QuoteLineItemCreate) -> QuoteLineItem:
        """Add a line item to a quote."""
        item = QuoteLineItem(
            quote_id=quote.id,
            description=data.description,
            quantity=data.quantity,
            unit_price=data.unit_price,
            discount=data.discount,
            sort_order=data.sort_order,
        )
        item.total = self._calculate_line_item_total(item)
        self.db.add(item)
        await self.db.flush()

        # Refresh to get updated line_items list
        await self.db.refresh(quote)
        self._recalculate_totals(quote)
        await self.db.flush()
        await self.db.refresh(item)

        return item

    async def remove_line_item(self, quote: Quote, item_id: int) -> None:
        """Remove a line item from a quote."""
        result = await self.db.execute(
            select(QuoteLineItem).where(
                QuoteLineItem.id == item_id,
                QuoteLineItem.quote_id == quote.id,
            )
        )
        item = result.scalar_one_or_none()
        if not item:
            raise ValueError(f"Line item {item_id} not found in quote {quote.id}")

        await self.db.delete(item)
        await self.db.flush()

        # Refresh and recalculate
        await self.db.refresh(quote)
        self._recalculate_totals(quote)
        await self.db.flush()

    async def send_quote_email(self, quote_id: int, user_id: int, attach_pdf: bool = False) -> Quote:
        """Send branded quote email to the contact's email address and mark as sent.

        If the quote has no contact with an email, the quote is still marked
        as sent but no email is dispatched.
        """
        quote = await self.get_by_id(quote_id)
        if not quote:
            raise ValueError(f"Quote {quote_id} not found")

        if quote.status not in self.valid_send_statuses:
            raise ValueError(f"Cannot transition from '{quote.status}' to 'sent'")

        # Send email only if quote has a contact with an email address
        if quote.contact and quote.contact.email:
            branding = await TenantBrandingHelper.get_branding_for_user(self.db, user_id)

            # Build public view URL for CTA button in email
            base_url = os.getenv("FRONTEND_URL", "http://localhost:3000")
            view_url = f"{base_url}/quotes/public/{quote.quote_number}"

            quote_data = {
                "quote_number": quote.quote_number,
                "client_name": quote.contact.full_name,
                "total": f"{float(quote.total):.2f}",
                "currency": quote.currency,
                "valid_until": str(quote.valid_until) if quote.valid_until else "",
                "items": [
                    {
                        "description": item.description,
                        "quantity": str(float(item.quantity)),
                        "unit_price": f"{float(item.unit_price):.2f}",
                        "total": f"{float(item.total):.2f}",
                    }
                    for item in quote.line_items
                ],
                "view_url": view_url,
            }

            subject, html_body = render_quote_email(branding, quote_data)

            email_service = EmailService(self.db)
            await email_service.queue_email(
                to_email=quote.contact.email,
                subject=subject,
                body=html_body,
                sent_by_id=user_id,
                entity_type="quotes",
                entity_id=quote.id,
            )

        quote.status = "sent"
        quote.sent_at = datetime.now(timezone.utc)
        await self.db.flush()
        await self.db.refresh(quote)

        return quote

    async def generate_quote_pdf(self, quote_id: int, user_id: int) -> bytes:
        """Generate branded quote PDF as HTML bytes."""
        quote = await self.get_by_id(quote_id)
        if not quote:
            raise ValueError(f"Quote {quote_id} not found")

        branding = await TenantBrandingHelper.get_branding_for_user(self.db, user_id)

        client_name = ""
        client_email = ""
        if quote.contact:
            client_name = quote.contact.full_name
            client_email = quote.contact.email or ""

        quote_data = {
            "quote_number": quote.quote_number,
            "date": str(quote.created_at.date()) if quote.created_at else "",
            "valid_until": str(quote.valid_until) if quote.valid_until else "",
            "client_name": client_name,
            "client_email": client_email,
            "client_address": "",
            "items": [
                {
                    "description": item.description,
                    "quantity": str(float(item.quantity)),
                    "unit_price": f"{float(item.unit_price):.2f}",
                    "total": f"{float(item.total):.2f}",
                }
                for item in quote.line_items
            ],
            "subtotal": f"{float(quote.subtotal):.2f}",
            "discount": f"{float(quote.discount_value):.2f}" if quote.discount_value else "",
            "tax": f"{float(quote.tax_amount):.2f}" if quote.tax_amount else "",
            "total": f"{float(quote.total):.2f}",
            "currency": quote.currency,
            "terms": quote.terms_and_conditions or "",
        }

        generator = BrandedPDFGenerator()
        return generator.generate_quote_pdf(quote_data, branding)

    async def get_public_quote(self, quote_number: str) -> Optional[Quote]:
        """Get a quote by its number for public viewing."""
        query = (
            select(Quote)
            .options(
                selectinload(Quote.line_items),
                selectinload(Quote.contact),
                selectinload(Quote.company),
            )
            .where(Quote.quote_number == quote_number)
        )
        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    async def get_branding_for_quote(self, quote: Quote) -> dict:
        """Get tenant branding from the quote owner's tenant."""
        if quote.owner_id:
            return await TenantBrandingHelper.get_branding_for_user(self.db, quote.owner_id)
        return TenantBrandingHelper.get_default_branding()

    async def record_quote_view(self, quote: Quote) -> Quote:
        """Record a view on a quote (auto-transition sent -> viewed)."""
        if quote.status == "sent":
            quote.status = "viewed"
        await self.db.flush()
        await self.db.refresh(quote)
        return quote

    async def accept_quote_public(
        self, quote: Quote, signer_name: str, signer_email: str, signer_ip: Optional[str] = None
    ) -> Quote:
        """Accept a quote via the public link with e-signature data."""
        if quote.status not in ("sent", "viewed"):
            raise ValueError(f"Cannot accept quote in '{quote.status}' status")

        now = datetime.now(timezone.utc)
        quote.status = "accepted"
        quote.accepted_at = now
        quote.signer_name = signer_name
        quote.signer_email = signer_email
        quote.signer_ip = signer_ip
        quote.signed_at = now
        await self.db.flush()
        await self.db.refresh(quote)
        return quote

    async def reject_quote_public(
        self, quote: Quote, reason: Optional[str] = None, signer_ip: Optional[str] = None
    ) -> Quote:
        """Reject a quote via the public link."""
        if quote.status not in ("sent", "viewed"):
            raise ValueError(f"Cannot reject quote in '{quote.status}' status")

        now = datetime.now(timezone.utc)
        quote.status = "rejected"
        quote.rejected_at = now
        quote.rejection_reason = reason
        quote.signer_ip = signer_ip
        await self.db.flush()
        await self.db.refresh(quote)
        return quote

    async def add_bundle_to_quote(self, quote: Quote, bundle_id: int) -> Quote:
        """Add all items from a product bundle to a quote as line items."""
        result = await self.db.execute(
            select(ProductBundle)
            .options(selectinload(ProductBundle.items))
            .where(ProductBundle.id == bundle_id)
        )
        bundle = result.scalar_one_or_none()
        if not bundle:
            raise ValueError(f"Product bundle {bundle_id} not found")
        if not bundle.is_active:
            raise ValueError(f"Product bundle {bundle_id} is not active")

        current_sort = len(quote.line_items)
        for bundle_item in bundle.items:
            item = QuoteLineItem(
                quote_id=quote.id,
                description=bundle_item.description,
                quantity=float(bundle_item.quantity),
                unit_price=float(bundle_item.unit_price),
                discount=0,
                sort_order=current_sort,
            )
            item.total = self._calculate_line_item_total(item)
            self.db.add(item)
            current_sort += 1

        await self.db.flush()
        await self.db.refresh(quote)
        self._recalculate_totals(quote)
        await self.db.flush()
        await self.db.refresh(quote)

        return quote


class ProductBundleService(BaseService[ProductBundle]):
    """Service for ProductBundle CRUD operations."""

    model = ProductBundle

    def _get_eager_load_options(self):
        return [selectinload(ProductBundle.items)]

    async def get_list(
        self,
        page: int = 1,
        page_size: int = DEFAULT_PAGE_SIZE,
        search: Optional[str] = None,
        is_active: Optional[bool] = None,
    ) -> Tuple[List[ProductBundle], int]:
        """Get paginated list of bundles."""
        query = select(ProductBundle).options(selectinload(ProductBundle.items))

        if search:
            search_condition = build_token_search(search, ProductBundle.name)
            if search_condition is not None:
                query = query.where(search_condition)
        if is_active is not None:
            query = query.where(ProductBundle.is_active == is_active)

        count_query = select(func.count()).select_from(query.subquery())
        total_result = await self.db.execute(count_query)
        total = total_result.scalar()

        offset = (page - 1) * page_size
        query = query.offset(offset).limit(page_size).order_by(ProductBundle.name)

        result = await self.db.execute(query)
        bundles = list(result.scalars().all())

        return bundles, total

    async def create(self, data: ProductBundleCreate, user_id: int) -> ProductBundle:
        """Create a product bundle with items."""
        items_data = data.items or []
        bundle = ProductBundle(
            name=data.name,
            description=data.description,
            is_active=data.is_active,
            created_by_id=user_id,
        )
        self.db.add(bundle)
        await self.db.flush()

        for item_data in items_data:
            item = ProductBundleItem(
                bundle_id=bundle.id,
                description=item_data.description,
                quantity=item_data.quantity,
                unit_price=item_data.unit_price,
                sort_order=item_data.sort_order,
            )
            self.db.add(item)

        await self.db.flush()
        await self.db.refresh(bundle)
        return bundle

    async def update(self, bundle: ProductBundle, data: ProductBundleUpdate, user_id: int) -> ProductBundle:
        """Update a product bundle, optionally replacing items."""
        if data.name is not None:
            bundle.name = data.name
        if data.description is not None:
            bundle.description = data.description
        if data.is_active is not None:
            bundle.is_active = data.is_active

        if data.items is not None:
            # Replace all items
            for old_item in bundle.items:
                await self.db.delete(old_item)
            await self.db.flush()

            for item_data in data.items:
                item = ProductBundleItem(
                    bundle_id=bundle.id,
                    description=item_data.description,
                    quantity=item_data.quantity,
                    unit_price=item_data.unit_price,
                    sort_order=item_data.sort_order,
                )
                self.db.add(item)

        await self.db.flush()
        await self.db.refresh(bundle)
        return bundle

    async def delete(self, bundle: ProductBundle) -> None:
        """Delete a product bundle."""
        await self.db.delete(bundle)
        await self.db.flush()
