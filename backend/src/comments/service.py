"""Comment service layer."""

import re
from typing import Optional, List, Tuple
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from src.comments.models import Comment
from src.core.constants import DEFAULT_PAGE_SIZE


def parse_mentions(content: str) -> List[str]:
    """Extract @mentions from comment content."""
    return re.findall(r"@(\w+(?:\.\w+)*)", content)


class CommentService:
    """Service for comment CRUD operations."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_id(self, comment_id: int) -> Optional[Comment]:
        """Get a comment by ID."""
        result = await self.db.execute(
            select(Comment).where(Comment.id == comment_id)
        )
        return result.scalar_one_or_none()

    async def get_entity_comments(
        self,
        entity_type: str,
        entity_id: int,
        page: int = 1,
        page_size: int = DEFAULT_PAGE_SIZE,
    ) -> Tuple[List[Comment], int]:
        """Get paginated top-level comments for an entity (replies loaded via selectin)."""
        base_filter = (
            Comment.entity_type == entity_type,
            Comment.entity_id == entity_id,
            Comment.parent_id.is_(None),
        )

        # Count
        count_query = select(func.count()).select_from(
            select(Comment.id).where(*base_filter).subquery()
        )
        total = (await self.db.execute(count_query)).scalar() or 0

        # Fetch
        offset = (page - 1) * page_size
        query = (
            select(Comment)
            .where(*base_filter)
            .order_by(Comment.created_at.desc())
            .offset(offset)
            .limit(page_size)
        )
        result = await self.db.execute(query)
        comments = result.scalars().all()

        return list(comments), total

    async def create(
        self,
        content: str,
        entity_type: str,
        entity_id: int,
        user_id: int,
        user_name: Optional[str] = None,
        user_email: Optional[str] = None,
        parent_id: Optional[int] = None,
        is_internal: bool = False,
    ) -> Comment:
        """Create a new comment."""
        comment = Comment(
            content=content,
            entity_type=entity_type,
            entity_id=entity_id,
            user_id=user_id,
            user_name=user_name,
            user_email=user_email,
            parent_id=parent_id,
            is_internal=is_internal,
        )
        self.db.add(comment)
        await self.db.flush()
        await self.db.refresh(comment)
        return comment

    async def update(self, comment: Comment, content: str) -> Comment:
        """Update a comment's content."""
        comment.content = content
        await self.db.flush()
        await self.db.refresh(comment)
        return comment

    async def delete(self, comment: Comment) -> None:
        """Delete a comment."""
        await self.db.delete(comment)
        await self.db.flush()
