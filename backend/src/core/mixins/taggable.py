"""
Taggable mixin for flexible tagging of any CRM entity.

Implements a polymorphic tagging system where any entity
can have tags attached via a junction table.
"""

from typing import TYPE_CHECKING, List
from sqlalchemy.orm import declared_attr, relationship, Mapped

if TYPE_CHECKING:
    from src.core.models import Tag


class TaggableMixin:
    """
    Mixin that enables tagging functionality on any CRM entity.

    Usage:
        class Contact(Base, TaggableMixin):
            __tablename__ = "contacts"
            ...

        # Access tags via: contact.tags
    """

    @declared_attr
    def tags(cls) -> Mapped[List["Tag"]]:
        """Relationship to tags for this entity via entity_tags junction."""
        return relationship(
            "Tag",
            secondary="entity_tags",
            primaryjoin=f"and_(EntityTag.entity_type=='{cls.__tablename__}', "
                        f"EntityTag.entity_id=={cls.__name__}.id)",
            secondaryjoin="EntityTag.tag_id==Tag.id",
            viewonly=True,
        )
