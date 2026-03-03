"""Tests for @mention processing in notes.

Validates:
- Creating a note with @mention creates a notification for the mentioned user
- Creating a note with @mention queues an email to the mentioned user
- Self-mentions are ignored (no notification for the author)
- Unknown usernames are ignored (no errors)
"""

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.models import User
from src.auth.security import get_password_hash, create_access_token
from src.contacts.models import Contact
from src.companies.models import Company
from src.core.models import Note
from src.notifications.models import Notification
from src.email.models import EmailQueue
from src.notes.service import NoteService
from src.notes.schemas import NoteCreate


class TestNotesMentionNotifications:
    """Test that @mentions in notes create notifications."""

    @pytest.mark.asyncio
    async def test_mention_creates_notification(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_user: User,
        test_contact: Contact,
    ):
        """Creating a note with @mention creates a notification for the mentioned user."""
        # Create a second user to be mentioned
        mentioned_user = User(
            email="mentioned@example.com",
            hashed_password=get_password_hash("password123"),
            full_name="Jane Smith",
            is_active=True,
        )
        db_session.add(mentioned_user)
        await db_session.commit()
        await db_session.refresh(mentioned_user)

        # Create a note mentioning the second user
        note_data = {
            "content": "Hey @Jane.Smith please review this contact",
            "entity_type": "contact",
            "entity_id": test_contact.id,
        }

        response = await client.post(
            "/api/notes",
            headers=auth_headers,
            json=note_data,
        )

        assert response.status_code == 201

        # Verify notification was created for the mentioned user
        result = await db_session.execute(
            select(Notification).where(
                Notification.user_id == mentioned_user.id,
                Notification.type == "mention",
            )
        )
        notification = result.scalar_one_or_none()

        assert notification is not None
        assert notification.user_id == mentioned_user.id
        assert notification.type == "mention"
        assert "mentioned in a note" in notification.title
        assert notification.entity_type == "contact"
        assert notification.entity_id == test_contact.id

    @pytest.mark.asyncio
    async def test_mention_sends_email(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_user: User,
        test_contact: Contact,
    ):
        """Creating a note with @mention queues an email to the mentioned user."""
        mentioned_user = User(
            email="emailme@example.com",
            hashed_password=get_password_hash("password123"),
            full_name="Bob Jones",
            is_active=True,
        )
        db_session.add(mentioned_user)
        await db_session.commit()
        await db_session.refresh(mentioned_user)

        note_data = {
            "content": "Check this out @Bob.Jones",
            "entity_type": "contact",
            "entity_id": test_contact.id,
        }

        response = await client.post(
            "/api/notes",
            headers=auth_headers,
            json=note_data,
        )

        assert response.status_code == 201

        # Verify email was queued
        result = await db_session.execute(
            select(EmailQueue).where(
                EmailQueue.to_email == "emailme@example.com",
                EmailQueue.subject == "You were mentioned in a note",
            )
        )
        email = result.scalar_one_or_none()

        assert email is not None
        assert email.to_email == "emailme@example.com"
        assert "mentioned in a note" in email.subject
        assert email.entity_type == "contact"
        assert email.entity_id == test_contact.id

    @pytest.mark.asyncio
    async def test_self_mention_ignored(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_user: User,
        test_contact: Contact,
    ):
        """Self-mentions should not create notifications."""
        # test_user.full_name is "Test User"
        note_data = {
            "content": "I am mentioning myself @Test.User",
            "entity_type": "contact",
            "entity_id": test_contact.id,
        }

        response = await client.post(
            "/api/notes",
            headers=auth_headers,
            json=note_data,
        )

        assert response.status_code == 201

        # Verify no notification was created for the author
        result = await db_session.execute(
            select(Notification).where(
                Notification.user_id == test_user.id,
                Notification.type == "mention",
            )
        )
        notifications = result.scalars().all()
        assert len(notifications) == 0

    @pytest.mark.asyncio
    async def test_unknown_username_ignored(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_user: User,
        test_contact: Contact,
    ):
        """Unknown @mention usernames should be silently ignored."""
        note_data = {
            "content": "Hey @Nonexistent.Person check this out",
            "entity_type": "contact",
            "entity_id": test_contact.id,
        }

        response = await client.post(
            "/api/notes",
            headers=auth_headers,
            json=note_data,
        )

        # Should succeed without errors
        assert response.status_code == 201

        # No mention notifications should be created
        result = await db_session.execute(
            select(Notification).where(Notification.type == "mention")
        )
        notifications = result.scalars().all()
        assert len(notifications) == 0
