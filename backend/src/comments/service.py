"""Comment service layer."""

import re
from typing import Optional, List, Tuple
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from src.comments.models import Comment
from src.auth.models import User
from src.core.constants import DEFAULT_PAGE_SIZE


# Regex to extract @mentions from comment content
MENTION_PATTERN = re.compile(r"@(\w+(?:\.\w+)*)")


def parse_mentions(content: str) -> List[str]:
    """Extract @mentioned usernames from comment content."""
    return MENTION_PATTERN.findall(content)


class CommentService:
    """Service for Comment CRUD operations."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_id(self, comment_id: int) -> Optional[Comment]:
        """Get a comment by ID."""
        result = await self.db.execute(
            select(Comment).where(Comment.id == comment_id)
        )
        return result.scalar_one_or_none()

    async def get_list(
        self,
        entity_type: str,
        entity_id: int,
        page: int = 1,
        page_size: int = DEFAULT_PAGE_SIZE,
    ) -> Tuple[List[dict], int]:
        """Get paginated list of top-level comments with author info and replies."""
        base_filter = [
            Comment.entity_type == entity_type,
            Comment.entity_id == entity_id,
            Comment.parent_id.is_(None),  # Only top-level comments
        ]

        # Count top-level comments
        count_query = select(func.count()).select_from(
            select(Comment.id).where(*base_filter).subquery()
        )
        total_result = await self.db.execute(count_query)
        total = total_result.scalar() or 0

        # Fetch top-level comments with author
        query = (
            select(Comment, User.full_name.label("author_name"))
            .outerjoin(User, Comment.user_id == User.id)
            .where(*base_filter)
            .order_by(Comment.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        result = await self.db.execute(query)
        rows = result.all()

        items = []
        for comment, author_name in rows:
            comment_dict = await self._build_comment_dict(comment, author_name)
            items.append(comment_dict)

        return items, total

    async def _build_comment_dict(self, comment: Comment, author_name: Optional[str] = None) -> dict:
        """Build a comment response dict with nested replies."""
        mentions = parse_mentions(comment.content)

        # Build replies recursively
        replies = []
        if comment.replies:
            for reply in comment.replies:
                # Get author name for reply
                reply_author = None
                if reply.user_id:
                    user_result = await self.db.execute(
                        select(User.full_name).where(User.id == reply.user_id)
                    )
                    reply_author = user_result.scalar_one_or_none()
                replies.append(await self._build_comment_dict(reply, reply_author))

        return {
            "id": comment.id,
            "content": comment.content,
            "entity_type": comment.entity_type,
            "entity_id": comment.entity_id,
            "user_id": comment.user_id,
            "author_name": author_name,
            "parent_id": comment.parent_id,
            "is_internal": comment.is_internal,
            "created_at": comment.created_at,
            "updated_at": comment.updated_at,
            "replies": replies,
            "mentions": mentions,
        }

    async def create(self, content: str, entity_type: str, entity_id: int,
                     user_id: int, parent_id: Optional[int] = None,
                     is_internal: bool = False) -> dict:
        """Create a new comment."""
        comment = Comment(
            content=content,
            entity_type=entity_type,
            entity_id=entity_id,
            user_id=user_id,
            parent_id=parent_id,
            is_internal=is_internal,
        )
        self.db.add(comment)
        await self.db.flush()
        await self.db.refresh(comment)

        # Get author name
        author_name = None
        if user_id:
            user_result = await self.db.execute(
                select(User.full_name).where(User.id == user_id)
            )
            author_name = user_result.scalar_one_or_none()

        return await self._build_comment_dict(comment, author_name)

    async def update(self, comment: Comment, content: str) -> dict:
        """Update a comment's content."""
        comment.content = content
        await self.db.flush()
        await self.db.refresh(comment)

        # Get author name
        author_name = None
        if comment.user_id:
            user_result = await self.db.execute(
                select(User.full_name).where(User.id == comment.user_id)
            )
            author_name = user_result.scalar_one_or_none()

        return await self._build_comment_dict(comment, author_name)

    async def delete(self, comment: Comment) -> None:
        """Delete a comment and its replies (cascade)."""
        await self.db.delete(comment)
        await self.db.flush()
