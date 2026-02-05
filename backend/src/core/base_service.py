"""Base service classes for DRY service layer implementation."""

from typing import TypeVar, Generic, Optional, List, Tuple, Type, Any, Dict
from collections import defaultdict
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload, InstrumentedAttribute
from pydantic import BaseModel
from src.core.models import Tag, EntityTag
from src.core.constants import DEFAULT_PAGE_SIZE

ModelType = TypeVar("ModelType")
CreateSchemaType = TypeVar("CreateSchemaType", bound=BaseModel)
UpdateSchemaType = TypeVar("UpdateSchemaType", bound=BaseModel)


class BaseService(Generic[ModelType]):
    """
    Base service providing common database operations.

    Provides:
    - get_by_id: Fetch single record by ID
    - get_multi: Fetch paginated list of records
    """

    model: Type[ModelType]

    def __init__(self, db: AsyncSession):
        self.db = db

    def _get_base_query(self):
        """Get base query with optional eager loading. Override in subclasses."""
        return select(self.model)

    def _get_eager_load_options(self) -> List[Any]:
        """Return list of selectinload options. Override in subclasses."""
        return []

    async def get_by_id(self, id: int) -> Optional[ModelType]:
        """Get a record by ID with optional eager loading."""
        query = select(self.model).where(self.model.id == id)

        for option in self._get_eager_load_options():
            query = query.options(option)

        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    async def get_multi(
        self,
        page: int = 1,
        page_size: int = DEFAULT_PAGE_SIZE,
        order_by: Optional[InstrumentedAttribute] = None,
        order_desc: bool = True,
    ) -> Tuple[List[ModelType], int]:
        """
        Get paginated list of records.

        Returns: (items, total_count)
        """
        query = self._get_base_query()

        for option in self._get_eager_load_options():
            query = query.options(option)

        # Get total count
        count_query = select(func.count()).select_from(query.subquery())
        total_result = await self.db.execute(count_query)
        total = total_result.scalar() or 0

        # Apply ordering
        if order_by is not None:
            query = query.order_by(order_by.desc() if order_desc else order_by.asc())
        elif hasattr(self.model, 'created_at'):
            query = query.order_by(self.model.created_at.desc())

        # Apply pagination
        offset = (page - 1) * page_size
        query = query.offset(offset).limit(page_size)

        result = await self.db.execute(query)
        items = list(result.scalars().all())

        return items, total


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
        """
        Create a new record.

        Args:
            data: Pydantic schema with creation data
            user_id: ID of user creating the record
            **extra_fields: Additional fields to set on the model
        """
        model_data = data.model_dump(exclude=self.create_exclude_fields)
        model_data.update(extra_fields)
        model_data["created_by_id"] = user_id

        instance = self.model(**model_data)
        self.db.add(instance)
        await self.db.flush()
        await self.db.refresh(instance)
        return instance

    async def update(
        self,
        instance: ModelType,
        data: UpdateSchemaType,
        user_id: int,
    ) -> ModelType:
        """
        Update an existing record.

        Args:
            instance: The model instance to update
            data: Pydantic schema with update data
            user_id: ID of user making the update
        """
        update_data = data.model_dump(exclude=self.update_exclude_fields, exclude_unset=True)

        for field, value in update_data.items():
            setattr(instance, field, value)

        if hasattr(instance, 'updated_by_id'):
            instance.updated_by_id = user_id

        await self.db.flush()
        await self.db.refresh(instance)
        return instance

    async def delete(self, instance: ModelType) -> None:
        """Delete a record."""
        await self.db.delete(instance)
        await self.db.flush()


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

    async def get_tags(self, entity_id: int) -> List[Tag]:
        """Get all tags for an entity."""
        result = await self.db.execute(
            select(Tag)
            .join(EntityTag)
            .where(EntityTag.entity_type == self.entity_type)
            .where(EntityTag.entity_id == entity_id)
        )
        return list(result.scalars().all())

    async def get_tags_for_entities(self, entity_ids: List[int]) -> Dict[int, List[Tag]]:
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
        tags_by_entity: Dict[int, List[Tag]] = defaultdict(list)
        for tag, entity_id in result.all():
            tags_by_entity[entity_id].append(tag)

        # Ensure all requested entity_ids have an entry (even if empty)
        return {entity_id: tags_by_entity.get(entity_id, []) for entity_id in entity_ids}

    async def update_tags(self, entity_id: int, tag_ids: List[int]) -> None:
        """
        Replace all tags for an entity.

        Removes existing tags and adds new ones.
        """
        # Remove existing tags
        await self.db.execute(
            EntityTag.__table__.delete().where(
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

    async def add_tags(self, entity_id: int, tag_ids: List[int]) -> None:
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

    async def remove_tags(self, entity_id: int, tag_ids: List[int]) -> None:
        """Remove specific tags from an entity."""
        await self.db.execute(
            EntityTag.__table__.delete().where(
                EntityTag.entity_type == self.entity_type,
                EntityTag.entity_id == entity_id,
                EntityTag.tag_id.in_(tag_ids),
            )
        )
        await self.db.flush()

    async def clear_tags(self, entity_id: int) -> None:
        """Remove all tags from an entity."""
        await self.db.execute(
            EntityTag.__table__.delete().where(
                EntityTag.entity_type == self.entity_type,
                EntityTag.entity_id == entity_id,
            )
        )
        await self.db.flush()

    async def _filter_by_tags(self, query, tag_ids: List[int]):
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
