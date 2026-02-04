"""Contact service layer."""

from typing import Optional, List, Tuple
from sqlalchemy import select, func, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from src.contacts.models import Contact
from src.contacts.schemas import ContactCreate, ContactUpdate
from src.core.models import Tag, EntityTag


class ContactService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_id(self, contact_id: int) -> Optional[Contact]:
        """Get contact by ID with related data."""
        result = await self.db.execute(
            select(Contact)
            .where(Contact.id == contact_id)
            .options(selectinload(Contact.company))
        )
        return result.scalar_one_or_none()

    async def get_list(
        self,
        page: int = 1,
        page_size: int = 20,
        search: Optional[str] = None,
        company_id: Optional[int] = None,
        status: Optional[str] = None,
        owner_id: Optional[int] = None,
        tag_ids: Optional[List[int]] = None,
    ) -> Tuple[List[Contact], int]:
        """Get paginated list of contacts with filters."""
        query = select(Contact).options(selectinload(Contact.company))

        # Apply filters
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
            query = query.where(Contact.owner_id == owner_id)

        if tag_ids:
            # Filter by tags using subquery
            tag_subquery = (
                select(EntityTag.entity_id)
                .where(EntityTag.entity_type == "contacts")
                .where(EntityTag.tag_id.in_(tag_ids))
                .group_by(EntityTag.entity_id)
                .having(func.count(EntityTag.tag_id) == len(tag_ids))
            )
            query = query.where(Contact.id.in_(tag_subquery))

        # Get total count
        count_query = select(func.count()).select_from(query.subquery())
        total_result = await self.db.execute(count_query)
        total = total_result.scalar()

        # Apply pagination
        offset = (page - 1) * page_size
        query = query.offset(offset).limit(page_size).order_by(Contact.created_at.desc())

        result = await self.db.execute(query)
        contacts = list(result.scalars().all())

        return contacts, total

    async def create(self, data: ContactCreate, user_id: int) -> Contact:
        """Create a new contact."""
        contact_data = data.model_dump(exclude={"tag_ids"})
        contact = Contact(**contact_data, created_by_id=user_id)
        self.db.add(contact)
        await self.db.flush()

        # Add tags
        if data.tag_ids:
            await self._update_tags(contact.id, data.tag_ids)

        await self.db.refresh(contact)
        return contact

    async def update(self, contact: Contact, data: ContactUpdate, user_id: int) -> Contact:
        """Update a contact."""
        update_data = data.model_dump(exclude={"tag_ids"}, exclude_unset=True)
        for field, value in update_data.items():
            setattr(contact, field, value)
        contact.updated_by_id = user_id
        await self.db.flush()

        # Update tags if provided
        if data.tag_ids is not None:
            await self._update_tags(contact.id, data.tag_ids)

        await self.db.refresh(contact)
        return contact

    async def delete(self, contact: Contact) -> None:
        """Delete a contact."""
        # Remove tag associations
        await self.db.execute(
            EntityTag.__table__.delete().where(
                EntityTag.entity_type == "contacts",
                EntityTag.entity_id == contact.id,
            )
        )
        await self.db.delete(contact)
        await self.db.flush()

    async def _update_tags(self, contact_id: int, tag_ids: List[int]) -> None:
        """Update tags for a contact."""
        # Remove existing tags
        await self.db.execute(
            EntityTag.__table__.delete().where(
                EntityTag.entity_type == "contacts",
                EntityTag.entity_id == contact_id,
            )
        )

        # Add new tags
        for tag_id in tag_ids:
            entity_tag = EntityTag(
                entity_type="contacts",
                entity_id=contact_id,
                tag_id=tag_id,
            )
            self.db.add(entity_tag)
        await self.db.flush()

    async def get_contact_tags(self, contact_id: int) -> List[Tag]:
        """Get tags for a contact."""
        result = await self.db.execute(
            select(Tag)
            .join(EntityTag)
            .where(EntityTag.entity_type == "contacts")
            .where(EntityTag.entity_id == contact_id)
        )
        return list(result.scalars().all())
