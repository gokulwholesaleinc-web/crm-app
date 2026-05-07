"""Base service classes for DRY service layer implementation."""

from collections import defaultdict
from datetime import UTC, datetime
from typing import Any, Generic, Protocol, TypeVar

from pydantic import BaseModel
from sqlalchemy import delete as sa_delete
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute

from src.core.constants import DEFAULT_PAGE_SIZE
from src.core.models import EntityTag, Tag


class _Entity(Protocol):
    id: Any


ModelType = TypeVar("ModelType", bound=_Entity)
CreateSchemaType = TypeVar("CreateSchemaType", bound=BaseModel)
UpdateSchemaType = TypeVar("UpdateSchemaType", bound=BaseModel)


class BaseService(Generic[ModelType]):
    """
    Base service providing common database operations.

    Provides:
    - get_by_id: Fetch single record by ID
    - get_multi: Fetch paginated list of records
    - paginate_query: Execute a query with pagination and count
    - apply_owner_filter: Filter by owner_id with shared entity support
    """

    model: type[ModelType]

    def __init__(self, db: AsyncSession):
        self.db = db

    def _get_base_query(self):
        """Get base query with optional eager loading. Override in subclasses."""
        return select(self.model)

    def _get_eager_load_options(self) -> list[Any]:
        """Return list of selectinload options. Override in subclasses."""
        return []

    async def get_by_id(self, id: int) -> ModelType | None:
        """Get a record by ID with optional eager loading."""
        query = select(self.model).where(self.model.id == id)

        for option in self._get_eager_load_options():
            query = query.options(option)

        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    async def paginate_query(
        self,
        query,
        page: int = 1,
        page_size: int = DEFAULT_PAGE_SIZE,
        order_by=None,
    ) -> tuple[list[ModelType], int]:
        """Execute a query with count and pagination. Returns (items, total)."""
        count_query = select(func.count()).select_from(query.subquery())
        total_result = await self.db.execute(count_query)
        total = total_result.scalar() or 0

        if order_by is not None:
            clauses = order_by if isinstance(order_by, list | tuple) else [order_by]
            query = query.order_by(*clauses)
        else:
            created_at = getattr(self.model, 'created_at', None)
            if created_at is not None:
                query = query.order_by(created_at.desc())

        offset = (page - 1) * page_size
        query = query.offset(offset).limit(page_size)

        result = await self.db.execute(query)
        items = list(result.scalars().all())
        return items, total

    def apply_owner_filter(self, query, owner_id: int | None, shared_entity_ids: list[int] | None = None):
        """Filter by owner_id, including shared entities if present.

        Only callable on services whose model has owner_id — not enforced at type level
        because not every BaseService subclass owns an owner_id column.
        """
        if not owner_id:
            return query
        model_owner_id: Any = self.model.owner_id  # type: ignore[attr-defined]
        if shared_entity_ids:
            return query.where(or_(model_owner_id == owner_id, self.model.id.in_(shared_entity_ids)))
        return query.where(model_owner_id == owner_id)

    async def get_multi(
        self,
        page: int = 1,
        page_size: int = DEFAULT_PAGE_SIZE,
        order_by: InstrumentedAttribute | None = None,
        order_desc: bool = True,
    ) -> tuple[list[ModelType], int]:
        """
        Get paginated list of records.

        Returns: (items, total_count)
        """
        query = self._get_base_query()

        for option in self._get_eager_load_options():
            query = query.options(option)

        sort_col = None
        if order_by is not None:
            sort_col = order_by.desc() if order_desc else order_by.asc()

        return await self.paginate_query(query, page, page_size, order_by=sort_col)


class CRUDService(BaseService[ModelType], Generic[ModelType, CreateSchemaType, UpdateSchemaType]):
    """
    CRUD service extending BaseService with create, update, delete operations.

    Provides:
    - All BaseService methods
    - create: Create new record
    - update: Update existing record
    - delete: Delete record
    """

    # Fields to exclude when creating/updating (e.g., tag_ids handled separately)
    create_exclude_fields: set = {"tag_ids"}
    update_exclude_fields: set = {"tag_ids"}

    async def create(
        self,
        data: CreateSchemaType,
        user_id: int,
        **extra_fields,
    ) -> ModelType:
        """Create a new record, auto-handling tags if TaggableServiceMixin is present."""
        model_data = data.model_dump(exclude=self.create_exclude_fields)
        model_data.update(extra_fields)
        model_data["created_by_id"] = user_id

        instance = self.model(**model_data)
        self.db.add(instance)
        await self.db.flush()
        await self.db.refresh(instance)

        # On create, an empty tag list means "no tags to apply" — skip.
        await self._apply_tags(instance, getattr(data, 'tag_ids', None), allow_empty=False)
        return instance

    async def update(
        self,
        instance: ModelType,
        data: UpdateSchemaType,
        user_id: int,
    ) -> ModelType:
        """Update an existing record, auto-handling tags if TaggableServiceMixin is present."""
        update_data = data.model_dump(exclude=self.update_exclude_fields, exclude_unset=True)

        for field, value in update_data.items():
            setattr(instance, field, value)

        if hasattr(instance, 'updated_by_id'):
            instance.updated_by_id = user_id  # type: ignore[attr-defined]

        await self.db.flush()
        await self.db.refresh(instance)

        # On update, an empty tag list means "clear all tags" — must run.
        await self._apply_tags(instance, getattr(data, 'tag_ids', None), allow_empty=True)
        return instance

    async def _apply_tags(
        self,
        instance: ModelType,
        tag_ids: list[int] | None,
        *,
        allow_empty: bool,
    ) -> None:
        update_tags = getattr(self, 'update_tags', None)
        if update_tags is None or tag_ids is None:
            return
        if not allow_empty and not tag_ids:
            return
        await update_tags(instance.id, tag_ids)
        await self.db.refresh(instance)

    async def delete(self, instance: ModelType) -> None:
        """Delete a record, clearing tags if TaggableServiceMixin is present."""
        clear_tags = getattr(self, 'clear_tags', None)
        if clear_tags:
            await clear_tags(instance.id)
        await self.db.delete(instance)
        await self.db.flush()



class StatusTransitionMixin:
    """
    Mixin providing status transition methods for entities with
    draft -> sent -> accepted/rejected workflows (quotes, proposals).

    Requires:
    - self.db: AsyncSession
    - Subclass may override class attributes to customize valid statuses.
    """

    db: AsyncSession

    valid_send_statuses: list = ["draft"]
    valid_accept_statuses: list = ["sent", "viewed"]
    valid_reject_statuses: list = ["sent", "viewed"]

    async def _transition_status(self, instance, target_status: str, valid_from: list, timestamp_attr: str):
        """Transition an entity to a new status with validation."""
        if instance.status not in valid_from:
            raise ValueError(f"Cannot transition from '{instance.status}' to '{target_status}'")
        instance.status = target_status
        setattr(instance, timestamp_attr, datetime.now(UTC))
        await self.db.flush()
        await self.db.refresh(instance)
        return instance

    async def mark_sent(self, instance):
        return await self._transition_status(instance, "sent", self.valid_send_statuses, "sent_at")

    async def mark_accepted(self, instance):
        return await self._transition_status(instance, "accepted", self.valid_accept_statuses, "accepted_at")

    async def mark_rejected(self, instance):
        return await self._transition_status(instance, "rejected", self.valid_reject_statuses, "rejected_at")


class TaggableServiceMixin:
    """
    Mixin providing tag management methods for services.

    Requires:
    - self.db: AsyncSession
    - self.entity_type: str (e.g., "contacts", "companies")

    Provides:
    - get_tags: Get all tags for an entity
    - get_tags_for_entities: Get tags for multiple entities in one query (solves N+1)
    - update_tags: Replace all tags for an entity
    - add_tags: Add tags to an entity
    - remove_tags: Remove tags from an entity
    """

    db: AsyncSession
    entity_type: str
    model: type[Any]

    async def get_tags(self, entity_id: int) -> list[Tag]:
        result = await self.db.execute(
            select(Tag)
            .join(EntityTag)
            .where(EntityTag.entity_type == self.entity_type)
            .where(EntityTag.entity_id == entity_id)
        )
        return list(result.scalars().all())

    async def get_tags_for_entities(self, entity_ids: list[int]) -> dict[int, list[Tag]]:
        """
        Get tags for multiple entities in a single query.

        Solves the N+1 query problem when listing entities with tags.

        Args:
            entity_ids: List of entity IDs to fetch tags for

        Returns:
            Dictionary mapping entity_id to list of Tag objects.
            Entities with no tags will have an empty list.
        """
        if not entity_ids:
            return {}

        # Single query to get all tags with their entity associations
        result = await self.db.execute(
            select(Tag, EntityTag.entity_id)
            .join(EntityTag)
            .where(EntityTag.entity_type == self.entity_type)
            .where(EntityTag.entity_id.in_(entity_ids))
        )

        # Group tags by entity_id
        tags_by_entity: dict[int, list[Tag]] = defaultdict(list)
        for tag, entity_id in result.all():
            tags_by_entity[entity_id].append(tag)

        # Ensure all requested entity_ids have an entry (even if empty)
        return {entity_id: tags_by_entity.get(entity_id, []) for entity_id in entity_ids}

    async def update_tags(self, entity_id: int, tag_ids: list[int]) -> None:
        """
        Replace all tags for an entity.

        Removes existing tags and adds new ones.
        """
        # Remove existing tags
        await self.db.execute(
            sa_delete(EntityTag).where(
                EntityTag.entity_type == self.entity_type,
                EntityTag.entity_id == entity_id,
            )
        )

        # Add new tags
        for tag_id in tag_ids:
            entity_tag = EntityTag(
                entity_type=self.entity_type,
                entity_id=entity_id,
                tag_id=tag_id,
            )
            self.db.add(entity_tag)

        await self.db.flush()

    async def add_tags(self, entity_id: int, tag_ids: list[int]) -> None:
        """Add tags to an entity (without removing existing tags)."""
        # Get existing tag IDs
        result = await self.db.execute(
            select(EntityTag.tag_id)
            .where(EntityTag.entity_type == self.entity_type)
            .where(EntityTag.entity_id == entity_id)
        )
        existing_tag_ids = set(result.scalars().all())

        # Add only new tags
        for tag_id in tag_ids:
            if tag_id not in existing_tag_ids:
                entity_tag = EntityTag(
                    entity_type=self.entity_type,
                    entity_id=entity_id,
                    tag_id=tag_id,
                )
                self.db.add(entity_tag)

        await self.db.flush()

    async def remove_tags(self, entity_id: int, tag_ids: list[int]) -> None:
        """Remove specific tags from an entity."""
        await self.db.execute(
            sa_delete(EntityTag).where(
                EntityTag.entity_type == self.entity_type,
                EntityTag.entity_id == entity_id,
                EntityTag.tag_id.in_(tag_ids),
            )
        )
        await self.db.flush()

    async def clear_tags(self, entity_id: int) -> None:
        """Remove all tags from an entity."""
        await self.db.execute(
            sa_delete(EntityTag).where(
                EntityTag.entity_type == self.entity_type,
                EntityTag.entity_id == entity_id,
            )
        )
        await self.db.flush()

    async def _filter_by_tags(self, query, tag_ids: list[int]):
        """
        Apply tag filter to a query.

        Filters for entities that have ALL specified tags.
        """
        tag_subquery = (
            select(EntityTag.entity_id)
            .where(EntityTag.entity_type == self.entity_type)
            .where(EntityTag.tag_id.in_(tag_ids))
            .group_by(EntityTag.entity_id)
            .having(func.count(EntityTag.tag_id) == len(tag_ids))
        )
        return query.where(self.model.id.in_(tag_subquery))
