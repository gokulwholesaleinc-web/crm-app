"""Contact service layer."""

from typing import Optional, List, Tuple, Any, Dict
from sqlalchemy import select, func, or_
from sqlalchemy.orm import selectinload
from src.contacts.models import Contact
from src.core.filtering import apply_filters_to_query
from src.contacts.schemas import ContactCreate, ContactUpdate
from src.core.base_service import CRUDService, TaggableServiceMixin
from src.core.constants import ENTITY_TYPE_CONTACTS, DEFAULT_PAGE_SIZE



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
        search: Optional[str] = None,
        company_id: Optional[int] = None,
        status: Optional[str] = None,
        owner_id: Optional[int] = None,
        tag_ids: Optional[List[int]] = None,
        filters: Optional[Dict[str, Any]] = None,
        shared_entity_ids: Optional[List[int]] = None,
    ) -> Tuple[List[Contact], int]:
        """Get paginated list of contacts with filters."""
        query = select(Contact).options(selectinload(Contact.company))

        if filters:
            query = apply_filters_to_query(query, Contact, filters)

        if search:
            search_filter = or_(
                Contact.first_name.ilike(f"%{search}%"),
                Contact.last_name.ilike(f"%{search}%"),
                Contact.email.ilike(f"%{search}%"),
            )
            query = query.where(search_filter)

        if company_id:
            query = query.where(Contact.company_id == company_id)

        if status:
            query = query.where(Contact.status == status)

        if owner_id:
            if shared_entity_ids:
                query = query.where(or_(Contact.owner_id == owner_id, Contact.id.in_(shared_entity_ids)))
            else:
                query = query.where(Contact.owner_id == owner_id)

        if tag_ids:
            query = await self._filter_by_tags(query, tag_ids)

        count_query = select(func.count()).select_from(query.subquery())
        total_result = await self.db.execute(count_query)
        total = total_result.scalar()

        offset = (page - 1) * page_size
        query = query.offset(offset).limit(page_size).order_by(Contact.created_at.desc())

        result = await self.db.execute(query)
        contacts = list(result.scalars().all())

        return contacts, total

    async def create(self, data: ContactCreate, user_id: int) -> Contact:
        """Create a new contact."""
        contact = await super().create(data, user_id)

        # Add tags
        if data.tag_ids:
            await self.update_tags(contact.id, data.tag_ids)
            await self.db.refresh(contact)

        return contact

    async def update(self, contact: Contact, data: ContactUpdate, user_id: int) -> Contact:
        """Update a contact."""
        contact = await super().update(contact, data, user_id)

        # Update tags if provided
        if data.tag_ids is not None:
            await self.update_tags(contact.id, data.tag_ids)
            await self.db.refresh(contact)

        return contact

    async def delete(self, contact: Contact) -> None:
        """Delete a contact."""
        # Remove tag associations
        await self.clear_tags(contact.id)
        await super().delete(contact)

