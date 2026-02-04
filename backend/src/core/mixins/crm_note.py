"""
CRMNote mixin - ERPNext pattern for shared note functionality.

This allows any entity (Lead, Contact, Opportunity) to have notes attached.
Notes support rich text content and are tracked with timestamps and author info.
"""

from datetime import datetime
from typing import TYPE_CHECKING, List
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, func
from sqlalchemy.orm import declared_attr, relationship, Mapped, mapped_column

if TYPE_CHECKING:
    from src.auth.models import User


class CRMNoteMixin:
    """
    Mixin that enables note functionality on any CRM entity.

    Based on ERPNext's CRMNote pattern - provides a unified way to attach
    notes to Leads, Contacts, Opportunities, etc.

    Usage:
        class Lead(Base, CRMNoteMixin):
            __tablename__ = "leads"
            ...

        # This will create a relationship to notes via the Note model
    """

    @declared_attr
    def notes(cls) -> Mapped[List["Note"]]:
        """Relationship to notes for this entity."""
        return relationship(
            "Note",
            primaryjoin=f"and_(Note.entity_type=='{cls.__tablename__}', "
                        f"Note.entity_id=={cls.__name__}.id)",
            foreign_keys="[Note.entity_id]",
            viewonly=True,
            lazy="dynamic",
        )


# Note model will be defined separately in a central location
# This is referenced by all entities using CRMNoteMixin
