"""Quote service layer."""

from datetime import datetime, timezone
from typing import Optional, List, Tuple
from sqlalchemy import select, func, or_
from sqlalchemy.orm import selectinload
from src.quotes.models import Quote, QuoteLineItem, QuoteTemplate
from src.quotes.schemas import QuoteCreate, QuoteUpdate, QuoteLineItemCreate
from src.core.base_service import CRUDService
from src.core.constants import DEFAULT_PAGE_SIZE

# Valid status transitions
VALID_TRANSITIONS = {
    "draft": ["sent"],
    "sent": ["viewed", "accepted", "rejected"],
    "viewed": ["accepted", "rejected"],
    "accepted": [],
    "rejected": [],
    "expired": [],
}


class QuoteService(CRUDService[Quote, QuoteCreate, QuoteUpdate]):
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
        return (item.quantity * item.unit_price) - item.discount

    def _recalculate_totals(self, quote: Quote) -> None:
        """Recalculate subtotal, tax_amount, and total from line items and discount."""
        subtotal = sum(
            self._calculate_line_item_total(item) for item in quote.line_items
        )
        quote.subtotal = subtotal

        # Apply quote-level discount
        discount_amount = 0.0
        if quote.discount_type == "percent" and quote.discount_value:
            discount_amount = subtotal * (quote.discount_value / 100)
        elif quote.discount_type == "fixed" and quote.discount_value:
            discount_amount = quote.discount_value

        after_discount = subtotal - discount_amount

        # Apply tax
        quote.tax_amount = after_discount * (quote.tax_rate / 100) if quote.tax_rate else 0
        quote.total = after_discount + quote.tax_amount

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
            query = query.where(
                or_(
                    Quote.title.ilike(f"%{search}%"),
                    Quote.quote_number.ilike(f"%{search}%"),
                )
            )

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

    def validate_status_transition(self, current_status: str, new_status: str) -> bool:
        """Check if a status transition is valid."""
        allowed = VALID_TRANSITIONS.get(current_status, [])
        return new_status in allowed

    async def mark_sent(self, quote: Quote) -> Quote:
        """Mark a quote as sent."""
        if not self.validate_status_transition(quote.status, "sent"):
            raise ValueError(f"Cannot transition from '{quote.status}' to 'sent'")
        quote.status = "sent"
        quote.sent_at = datetime.now(timezone.utc)
        await self.db.flush()
        await self.db.refresh(quote)
        return quote

    async def mark_accepted(self, quote: Quote) -> Quote:
        """Mark a quote as accepted."""
        if not self.validate_status_transition(quote.status, "accepted"):
            raise ValueError(f"Cannot transition from '{quote.status}' to 'accepted'")
        quote.status = "accepted"
        quote.accepted_at = datetime.now(timezone.utc)
        await self.db.flush()
        await self.db.refresh(quote)
        return quote

    async def mark_rejected(self, quote: Quote) -> Quote:
        """Mark a quote as rejected."""
        if not self.validate_status_transition(quote.status, "rejected"):
            raise ValueError(f"Cannot transition from '{quote.status}' to 'rejected'")
        quote.status = "rejected"
        quote.rejected_at = datetime.now(timezone.utc)
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
