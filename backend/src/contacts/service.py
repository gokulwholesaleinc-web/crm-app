"""Contact service layer."""

import logging
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.orm import selectinload

from src.contacts.models import Contact
from src.contacts.schemas import ContactCreate, ContactUpdate
from src.core.base_service import CRUDService, TaggableServiceMixin
from src.core.constants import DEFAULT_PAGE_SIZE, ENTITY_TYPE_CONTACTS
from src.core.filtering import apply_filters_to_query, build_token_search

logger = logging.getLogger(__name__)


class ContactService(
    CRUDService[Contact, ContactCreate, ContactUpdate],
    TaggableServiceMixin,
):
    """Service for Contact CRUD operations with tag support."""

    model = Contact
    entity_type = ENTITY_TYPE_CONTACTS

    def _get_eager_load_options(self):
        """Load company relation."""
        return [selectinload(Contact.company)]

    async def get_list(
        self,
        page: int = 1,
        page_size: int = DEFAULT_PAGE_SIZE,
        search: str | None = None,
        company_id: int | None = None,
        status: str | None = None,
        owner_id: int | None = None,
        tag_ids: list[int] | None = None,
        filters: dict[str, Any] | None = None,
        shared_entity_ids: list[int] | None = None,
    ) -> tuple[list[Contact], int]:
        """Get paginated list of contacts with filters.

        Soft-deleted contacts (``deleted_at IS NOT NULL``) are hidden unless
        the caller explicitly passes ``status="archived"`` — in which case
        only archived rows are returned, matching the UX of a "trash" view.
        """
        query = select(Contact).options(selectinload(Contact.company))

        if filters:
            query = apply_filters_to_query(query, Contact, filters)

        if search:
            search_condition = build_token_search(search, Contact.first_name, Contact.last_name, Contact.email)
            if search_condition is not None:
                query = query.where(search_condition)

        if company_id:
            query = query.where(Contact.company_id == company_id)

        if status == "archived":
            query = query.where(Contact.deleted_at.is_not(None))
        else:
            query = query.where(Contact.deleted_at.is_(None))
            if status:
                query = query.where(Contact.status == status)

        query = self.apply_owner_filter(query, owner_id, shared_entity_ids)

        if tag_ids:
            query = await self._filter_by_tags(query, tag_ids)

        return await self.paginate_query(query, page, page_size)

    async def update(
        self,
        instance: Contact,
        data: ContactUpdate,
        user_id: int,
    ) -> Contact:
        """Update a contact and cascade owner_id changes to linked records.

        When the owner changes, every Proposal / Quote / Opportunity /
        Payment that was assigned to the same old owner via this contact
        gets re-assigned to the new owner in the same transaction. This
        keeps "my pipeline" lists in sync — without it, a rep handoff left
        the new owner blind to the deals they just inherited.
        """
        old_owner_id = instance.owner_id
        new_owner_id = data.owner_id if "owner_id" in data.model_fields_set else old_owner_id

        contact = await super().update(instance, data, user_id)

        if (
            new_owner_id is not None
            and old_owner_id is not None
            and new_owner_id != old_owner_id
        ):
            await self._cascade_owner_change(contact.id, old_owner_id, new_owner_id)

        return contact

    async def _cascade_owner_change(
        self,
        contact_id: int,
        old_owner_id: int,
        new_owner_id: int,
    ) -> None:
        """Re-assign linked Proposal/Quote/Opportunity/Payment rows whose
        owner matches ``old_owner_id``. Runs inside the caller's transaction.
        """
        from src.opportunities.models import Opportunity
        from src.payments.models import Payment, StripeCustomer
        from src.proposals.models import Proposal
        from src.quotes.models import Quote

        proposal_result = await self.db.execute(
            update(Proposal)
            .where(Proposal.contact_id == contact_id)
            .where(Proposal.owner_id == old_owner_id)
            .values(owner_id=new_owner_id)
        )
        quote_result = await self.db.execute(
            update(Quote)
            .where(Quote.contact_id == contact_id)
            .where(Quote.owner_id == old_owner_id)
            .values(owner_id=new_owner_id)
        )
        opportunity_result = await self.db.execute(
            update(Opportunity)
            .where(Opportunity.contact_id == contact_id)
            .where(Opportunity.owner_id == old_owner_id)
            .values(owner_id=new_owner_id)
        )
        # Payments are linked to a contact through StripeCustomer.contact_id,
        # not directly. Scope the update to payments whose customer points
        # at this contact.
        customer_subquery = (
            select(StripeCustomer.id).where(StripeCustomer.contact_id == contact_id)
        )
        payment_result = await self.db.execute(
            update(Payment)
            .where(Payment.customer_id.in_(customer_subquery))
            .where(Payment.owner_id == old_owner_id)
            .values(owner_id=new_owner_id)
        )
        await self.db.flush()

        logger.info(
            "Cascaded owner change for contact %d: %d proposals, %d quotes, "
            "%d opportunities, %d payments",
            contact_id,
            proposal_result.rowcount or 0,
            quote_result.rowcount or 0,
            opportunity_result.rowcount or 0,
            payment_result.rowcount or 0,
        )

    async def soft_delete(self, contact: Contact) -> Contact:
        """Soft-delete a contact by setting ``deleted_at`` and ``status``.

        Never hard-deletes: the row is kept so AR ledger, activities, and
        invoice history referencing this contact stay intact. Idempotent —
        calling on an already-archived contact is a no-op.

        The email is prefixed with ``archived-<id>-`` rather than cleared
        so that (a) the unique constraint on ``contacts.email`` no longer
        blocks a new contact from reusing the original address, and
        (b) the original email remains recoverable (e.g. un-archive
        workflow, support lookups) by stripping the prefix.
        """
        if contact.deleted_at is None:
            contact.deleted_at = datetime.now(UTC)
            contact.status = "archived"
            if contact.email and not contact.email.startswith("archived-"):
                prefix = f"archived-{contact.id}-"
                # Truncate to fit the 255-char column width.
                contact.email = (prefix + contact.email)[:255]
            await self.db.flush()
        return contact

    async def get_payment_summary(self, contact_id: int) -> dict:
        """Get payment summary for a contact via their StripeCustomer link."""
        from src.payments.models import Payment, StripeCustomer

        empty_summary = {
            "total_paid": 0.0,
            "payment_count": 0,
            "late_payments": 0,
            "on_time_rate": 100.0,
            "last_payment_date": None,
        }

        # Find StripeCustomer records linked to this contact
        customer_result = await self.db.execute(
            select(StripeCustomer.id).where(StripeCustomer.contact_id == contact_id)
        )
        customer_ids = [row[0] for row in customer_result.fetchall()]

        if not customer_ids:
            return empty_summary

        # Query all payments for these customers
        all_result = await self.db.execute(
            select(Payment).where(Payment.customer_id.in_(customer_ids))
        )
        all_payments = list(all_result.scalars().all())

        if not all_payments:
            return empty_summary

        succeeded = [p for p in all_payments if p.status == "succeeded"]
        if not succeeded:
            late_payments = sum(1 for p in all_payments if p.status == "failed")
            total_attempts = len(all_payments)
            return {
                **empty_summary,
                "late_payments": late_payments,
                "on_time_rate": round(((total_attempts - late_payments) / total_attempts) * 100, 1) if total_attempts > 0 else 100.0,
            }

        total_paid = sum(float(p.amount) for p in succeeded)
        late_payments = sum(1 for p in all_payments if p.status == "failed")
        total_attempts = len(all_payments)
        on_time_rate = round(((total_attempts - late_payments) / total_attempts) * 100, 1) if total_attempts > 0 else 100.0
        last_payment_date = max((p.created_at for p in succeeded), default=None)

        return {
            "total_paid": round(total_paid, 2),
            "payment_count": len(succeeded),
            "late_payments": late_payments,
            "on_time_rate": on_time_rate,
            "last_payment_date": last_payment_date.isoformat() if last_payment_date else None,
        }

