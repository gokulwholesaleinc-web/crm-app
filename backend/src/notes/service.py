"""Note service layer."""

from typing import Optional, List, Tuple
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from src.core.models import Note
from src.auth.models import User
from src.comments.service import parse_mentions
from src.notes.schemas import NoteCreate, NoteUpdate
from src.core.constants import DEFAULT_PAGE_SIZE


class NoteService:
    """Service for Note CRUD operations."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_id(self, note_id: int) -> Optional[Note]:
        """Get a note by ID."""
        result = await self.db.execute(
            select(Note).where(Note.id == note_id)
        )
        return result.scalar_one_or_none()

    async def get_list(
        self,
        page: int = 1,
        page_size: int = DEFAULT_PAGE_SIZE,
        entity_type: Optional[str] = None,
        entity_id: Optional[int] = None,
        created_by_id: Optional[int] = None,
    ) -> Tuple[List[dict], int]:
        """Get paginated list of notes with author info."""
        query = (
            select(Note, User.full_name.label("author_name"))
            .outerjoin(User, Note.created_by_id == User.id)
        )

        if entity_type:
            query = query.where(Note.entity_type == entity_type)

        if entity_id:
            query = query.where(Note.entity_id == entity_id)

        if created_by_id:
            query = query.where(Note.created_by_id == created_by_id)

        # Get total count using same filters
        count_base_query = select(Note.id)
        if entity_type:
            count_base_query = count_base_query.where(Note.entity_type == entity_type)
        if entity_id:
            count_base_query = count_base_query.where(Note.entity_id == entity_id)
        if created_by_id:
            count_base_query = count_base_query.where(Note.created_by_id == created_by_id)

        count_query = select(func.count()).select_from(count_base_query.subquery())
        total_result = await self.db.execute(count_query)
        total = total_result.scalar() or 0

        # Apply ordering and pagination
        offset = (page - 1) * page_size
        query = query.order_by(Note.created_at.desc()).offset(offset).limit(page_size)

        result = await self.db.execute(query)
        rows = result.all()

        # Build response with author names
        notes = []
        for note, author_name in rows:
            note_dict = {
                "id": note.id,
                "content": note.content,
                "entity_type": note.entity_type,
                "entity_id": note.entity_id,
                "created_by_id": note.created_by_id,
                "created_at": note.created_at,
                "updated_at": note.updated_at,
                "author_name": author_name,
            }
            notes.append(note_dict)

        return notes, total

    async def create(self, data: NoteCreate, user_id: int) -> dict:
        """Create a new note."""
        note = Note(
            content=data.content,
            entity_type=data.entity_type,
            entity_id=data.entity_id,
            created_by_id=user_id,
        )
        self.db.add(note)
        await self.db.flush()
        await self.db.refresh(note)

        # Get author name
        author_name = None
        if user_id:
            user_result = await self.db.execute(
                select(User.full_name).where(User.id == user_id)
            )
            author_name = user_result.scalar_one_or_none()

        # Parse @mentions and notify
        await self._process_mentions(note, user_id)

        return {
            "id": note.id,
            "content": note.content,
            "entity_type": note.entity_type,
            "entity_id": note.entity_id,
            "created_by_id": note.created_by_id,
            "created_at": note.created_at,
            "updated_at": note.updated_at,
            "author_name": author_name,
        }

    async def _process_mentions(self, note: Note, author_id: int) -> None:
        """Parse @mentions from note content and create notifications + emails."""
        from src.notifications.service import NotificationService
        from src.email.service import EmailService

        usernames = parse_mentions(note.content)
        if not usernames:
            return

        for username in usernames:
            full_name = username.replace('.', ' ')
            # Normalize whitespace: match even if DB has extra spaces
            user_result = await self.db.execute(
                select(User).where(
                    func.lower(func.regexp_replace(User.full_name, r'\s+', ' ', 'g'))
                    == func.lower(full_name)
                )
            )
            mentioned_user = user_result.scalar_one_or_none()
            if not mentioned_user or mentioned_user.id == author_id:
                continue

            notif_service = NotificationService(self.db)
            await notif_service.create_notification(
                user_id=mentioned_user.id,
                type="mention",
                title="You were mentioned in a note",
                message=f"You were mentioned in a note: {note.content[:100]}",
                entity_type=note.entity_type,
                entity_id=note.entity_id,
            )

            if mentioned_user.email:
                email_service = EmailService(self.db)
                await email_service.queue_email(
                    to_email=mentioned_user.email,
                    subject="You were mentioned in a note",
                    body=f"<p>You were mentioned in a note:</p><blockquote>{note.content}</blockquote>",
                    sent_by_id=author_id,
                    entity_type=note.entity_type,
                    entity_id=note.entity_id,
                )

    async def update(self, note: Note, data: NoteUpdate, user_id: int) -> dict:
        """Update a note."""
        if data.content is not None:
            note.content = data.content

        await self.db.flush()
        await self.db.refresh(note)

        # Get author name
        author_name = None
        if note.created_by_id:
            user_result = await self.db.execute(
                select(User.full_name).where(User.id == note.created_by_id)
            )
            author_name = user_result.scalar_one_or_none()

        return {
            "id": note.id,
            "content": note.content,
            "entity_type": note.entity_type,
            "entity_id": note.entity_id,
            "created_by_id": note.created_by_id,
            "created_at": note.created_at,
            "updated_at": note.updated_at,
            "author_name": author_name,
        }

    async def delete(self, note: Note) -> None:
        """Delete a note."""
        await self.db.delete(note)
        await self.db.flush()
