"""Comment model for team collaboration."""

from datetime import datetime
from typing import Optional, List
from sqlalchemy import String, Integer, ForeignKey, Text, Boolean, DateTime, func, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from src.database import Base
from src.core.mixins.auditable import TimestampMixin


class Comment(Base, TimestampMixin):
    """Comment model - polymorphic comments with threading and @mentions."""
    __tablename__ = "comments"

    id: Mapped[int] = mapped_column(primary_key=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)

    # Polymorphic link to any entity
    entity_type: Mapped[str] = mapped_column(String(50), nullable=False)
    entity_id: Mapped[int] = mapped_column(Integer, nullable=False)

    # Author
    user_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Threading - parent_id for replies
    parent_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("comments.id", ondelete="CASCADE"),
        nullable=True,
    )

    # Internal flag - only visible to team members
    is_internal: Mapped[bool] = mapped_column(Boolean, default=False)

    # Self-referential relationship for threading
    replies: Mapped[List["Comment"]] = relationship(
        "Comment",
        back_populates="parent",
        lazy="selectin",
        order_by="Comment.created_at",
        cascade="all, delete-orphan",
    )
    parent: Mapped[Optional["Comment"]] = relationship(
        "Comment",
        back_populates="replies",
        remote_side=[id],
        lazy="select",
    )

    __table_args__ = (
        Index("ix_comments_entity", "entity_type", "entity_id"),
        Index("ix_comments_parent", "parent_id"),
        Index("ix_comments_user", "user_id"),
    )
