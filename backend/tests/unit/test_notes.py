"""
Unit tests for notes CRUD endpoints.

Tests for list, create, get, update, and delete operations.
"""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.models import User
from src.core.models import Note
from src.contacts.models import Contact


class TestNotesList:
    """Tests for notes list endpoint with pagination."""

    @pytest.mark.asyncio
    async def test_list_notes_empty(
        self, client: AsyncClient, db_session: AsyncSession, auth_headers: dict
    ):
        """Test listing notes when none exist."""
        response = await client.get("/api/notes", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["items"] == []
        assert data["total"] == 0
        assert data["page"] == 1

    @pytest.mark.asyncio
    async def test_list_notes_with_data(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_note: Note,
    ):
        """Test listing notes with existing data."""
        response = await client.get("/api/notes", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["total"] >= 1
        assert len(data["items"]) >= 1
        assert any(n["id"] == test_note.id for n in data["items"])

    @pytest.mark.asyncio
    async def test_list_notes_pagination(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_user: User,
        test_contact: Contact,
    ):
        """Test notes pagination."""
        # Create multiple notes
        for i in range(15):
            note = Note(
                content=f"Note content {i}",
                entity_type="contact",
                entity_id=test_contact.id,
                created_by_id=test_user.id,
            )
            db_session.add(note)
        await db_session.commit()

        # First page
        response = await client.get(
            "/api/notes",
            headers=auth_headers,
            params={"page": 1, "page_size": 10},
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 10
        assert data["page"] == 1
        assert data["total"] >= 15

        # Second page
        response = await client.get(
            "/api/notes",
            headers=auth_headers,
            params={"page": 2, "page_size": 10},
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) >= 5

    @pytest.mark.asyncio
    async def test_list_notes_filter_by_entity(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_note: Note,
        test_contact: Contact,
    ):
        """Test filtering notes by entity type and ID."""
        response = await client.get(
            "/api/notes",
            headers=auth_headers,
            params={
                "entity_type": "contact",
                "entity_id": test_contact.id,
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert all(
            n["entity_type"] == "contact" and n["entity_id"] == test_contact.id
            for n in data["items"]
        )


class TestNotesCreate:
    """Tests for note creation endpoint."""

    @pytest.mark.asyncio
    async def test_create_note_success(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_contact: Contact,
    ):
        """Test successful note creation."""
        note_data = {
            "content": "This is a new note",
            "entity_type": "contact",
            "entity_id": test_contact.id,
        }

        response = await client.post(
            "/api/notes",
            headers=auth_headers,
            json=note_data,
        )

        assert response.status_code == 201
        data = response.json()
        assert data["content"] == note_data["content"]
        assert data["entity_type"] == note_data["entity_type"]
        assert data["entity_id"] == note_data["entity_id"]
        assert "id" in data
        assert "created_at" in data

    @pytest.mark.asyncio
    async def test_create_note_missing_content(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_contact: Contact,
    ):
        """Test note creation with missing content."""
        note_data = {
            "entity_type": "contact",
            "entity_id": test_contact.id,
        }

        response = await client.post(
            "/api/notes",
            headers=auth_headers,
            json=note_data,
        )

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_create_note_with_author_name(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_contact: Contact,
        test_user: User,
    ):
        """Test that created note includes author name."""
        note_data = {
            "content": "Note with author",
            "entity_type": "contact",
            "entity_id": test_contact.id,
        }

        response = await client.post(
            "/api/notes",
            headers=auth_headers,
            json=note_data,
        )

        assert response.status_code == 201
        data = response.json()
        assert data["author_name"] == test_user.full_name
        assert data["created_by_id"] == test_user.id


class TestNotesGet:
    """Tests for getting a single note."""

    @pytest.mark.asyncio
    async def test_get_note_success(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_note: Note,
    ):
        """Test getting a note by ID."""
        response = await client.get(
            f"/api/notes/{test_note.id}",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == test_note.id
        assert data["content"] == test_note.content

    @pytest.mark.asyncio
    async def test_get_note_not_found(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
    ):
        """Test getting a non-existent note."""
        response = await client.get(
            "/api/notes/99999",
            headers=auth_headers,
        )

        assert response.status_code == 404


class TestNotesUpdate:
    """Tests for note update endpoint."""

    @pytest.mark.asyncio
    async def test_update_note_success(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_note: Note,
    ):
        """Test successful note update."""
        update_data = {"content": "Updated note content"}

        response = await client.patch(
            f"/api/notes/{test_note.id}",
            headers=auth_headers,
            json=update_data,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["content"] == update_data["content"]

    @pytest.mark.asyncio
    async def test_update_note_not_found(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
    ):
        """Test updating a non-existent note."""
        update_data = {"content": "Updated content"}

        response = await client.patch(
            "/api/notes/99999",
            headers=auth_headers,
            json=update_data,
        )

        assert response.status_code == 404


class TestNotesDelete:
    """Tests for note delete endpoint."""

    @pytest.mark.asyncio
    async def test_delete_note_success(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_note: Note,
    ):
        """Test successful note deletion."""
        response = await client.delete(
            f"/api/notes/{test_note.id}",
            headers=auth_headers,
        )

        assert response.status_code == 204

        # Verify deletion
        response = await client.get(
            f"/api/notes/{test_note.id}",
            headers=auth_headers,
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_note_not_found(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
    ):
        """Test deleting a non-existent note."""
        response = await client.delete(
            "/api/notes/99999",
            headers=auth_headers,
        )

        assert response.status_code == 404


class TestNotesPermissions:
    """Tests for note permissions."""

    @pytest.mark.asyncio
    async def test_cannot_update_other_users_note(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_contact: Contact,
    ):
        """Test that users cannot update notes created by others."""
        from src.auth.security import get_password_hash, create_access_token

        # Create another user
        other_user = User(
            email="other@example.com",
            hashed_password=get_password_hash("password123"),
            full_name="Other User",
            is_active=True,
        )
        db_session.add(other_user)
        await db_session.commit()
        await db_session.refresh(other_user)

        # Create note with the other user
        note = Note(
            content="Other user's note",
            entity_type="contact",
            entity_id=test_contact.id,
            created_by_id=other_user.id,
        )
        db_session.add(note)
        await db_session.commit()
        await db_session.refresh(note)

        # Create test user and auth headers
        test_user = User(
            email="testuser2@example.com",
            hashed_password=get_password_hash("password123"),
            full_name="Test User 2",
            is_active=True,
        )
        db_session.add(test_user)
        await db_session.commit()
        await db_session.refresh(test_user)

        token = create_access_token(data={"sub": str(test_user.id)})
        headers = {"Authorization": f"Bearer {token}"}

        # Try to update the note
        response = await client.patch(
            f"/api/notes/{note.id}",
            headers=headers,
            json={"content": "Trying to update"},
        )

        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_cannot_delete_other_users_note(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_contact: Contact,
    ):
        """Test that users cannot delete notes created by others."""
        from src.auth.security import get_password_hash, create_access_token

        # Create another user
        other_user = User(
            email="other2@example.com",
            hashed_password=get_password_hash("password123"),
            full_name="Other User 2",
            is_active=True,
        )
        db_session.add(other_user)
        await db_session.commit()
        await db_session.refresh(other_user)

        # Create note with the other user
        note = Note(
            content="Other user's note to delete",
            entity_type="contact",
            entity_id=test_contact.id,
            created_by_id=other_user.id,
        )
        db_session.add(note)
        await db_session.commit()
        await db_session.refresh(note)

        # Create test user and auth headers
        test_user = User(
            email="testuser3@example.com",
            hashed_password=get_password_hash("password123"),
            full_name="Test User 3",
            is_active=True,
        )
        db_session.add(test_user)
        await db_session.commit()
        await db_session.refresh(test_user)

        token = create_access_token(data={"sub": str(test_user.id)})
        headers = {"Authorization": f"Bearer {token}"}

        # Try to delete the note
        response = await client.delete(
            f"/api/notes/{note.id}",
            headers=headers,
        )

        assert response.status_code == 403
