"""
Unit tests for comments/team collaboration endpoints.

Tests for comment creation, listing, threading, @mentions, and deletion.
"""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from src.auth.models import User
from src.contacts.models import Contact
from src.companies.models import Company
from src.comments.models import Comment
from src.comments.service import CommentService, parse_mentions


class TestParseMentions:
    """Tests for the @mention parsing utility."""

    def test_parse_single_mention(self):
        """Test extracting a single @mention."""
        mentions = parse_mentions("Hello @john please review")
        assert mentions == ["john"]

    def test_parse_multiple_mentions(self):
        """Test extracting multiple @mentions."""
        mentions = parse_mentions("@alice and @bob should look at this")
        assert len(mentions) == 2
        assert "alice" in mentions
        assert "bob" in mentions

    def test_parse_no_mentions(self):
        """Test parsing text without mentions."""
        mentions = parse_mentions("No mentions here")
        assert mentions == []

    def test_parse_mention_with_dots(self):
        """Test parsing @mentions with dots (email-like)."""
        mentions = parse_mentions("CC @john.doe on this")
        assert mentions == ["john.doe"]

    def test_parse_mention_at_start(self):
        """Test @mention at start of text."""
        mentions = parse_mentions("@admin please check")
        assert mentions == ["admin"]


class TestCommentService:
    """Tests for the comment service layer."""

    @pytest.mark.asyncio
    async def test_create_comment(
        self,
        db_session: AsyncSession,
        test_user: User,
        test_contact: Contact,
    ):
        """Test creating a comment."""
        service = CommentService(db_session)
        comment = await service.create(
            content="This is a test comment",
            entity_type="contact",
            entity_id=test_contact.id,
            user_id=test_user.id,
        )
        assert comment["id"] is not None
        assert comment["content"] == "This is a test comment"
        assert comment["entity_type"] == "contact"
        assert comment["user_id"] == test_user.id

    @pytest.mark.asyncio
    async def test_create_internal_comment(
        self,
        db_session: AsyncSession,
        test_user: User,
        test_contact: Contact,
    ):
        """Test creating an internal comment."""
        service = CommentService(db_session)
        comment = await service.create(
            content="Internal note",
            entity_type="contact",
            entity_id=test_contact.id,
            user_id=test_user.id,
            is_internal=True,
        )
        assert comment["is_internal"] is True

    @pytest.mark.asyncio
    async def test_create_reply(
        self,
        db_session: AsyncSession,
        test_user: User,
        test_contact: Contact,
    ):
        """Test creating a reply to a comment."""
        service = CommentService(db_session)
        parent = await service.create(
            content="Parent comment",
            entity_type="contact",
            entity_id=test_contact.id,
            user_id=test_user.id,
        )

        reply = await service.create(
            content="This is a reply",
            entity_type="contact",
            entity_id=test_contact.id,
            user_id=test_user.id,
            parent_id=parent["id"],
        )
        assert reply["parent_id"] == parent["id"]

    @pytest.mark.asyncio
    async def test_list_comments(
        self,
        db_session: AsyncSession,
        test_user: User,
        test_contact: Contact,
    ):
        """Test listing comments for an entity."""
        service = CommentService(db_session)

        await service.create("Comment 1", "contact", test_contact.id, test_user.id)
        await service.create("Comment 2", "contact", test_contact.id, test_user.id)
        await service.create("Comment 3", "contact", test_contact.id, test_user.id)

        items, total = await service.get_list("contact", test_contact.id)
        assert total == 3
        assert len(items) == 3

    @pytest.mark.asyncio
    async def test_list_comments_excludes_replies(
        self,
        db_session: AsyncSession,
        test_user: User,
        test_contact: Contact,
    ):
        """Test that listing returns only top-level comments, not replies."""
        service = CommentService(db_session)

        parent = await service.create("Parent", "contact", test_contact.id, test_user.id)
        await service.create("Reply", "contact", test_contact.id, test_user.id, parent_id=parent["id"])

        items, total = await service.get_list("contact", test_contact.id)
        assert total == 1  # Only the parent

    @pytest.mark.asyncio
    async def test_comment_includes_mentions(
        self,
        db_session: AsyncSession,
        test_user: User,
        test_contact: Contact,
    ):
        """Test that comment response includes parsed mentions."""
        service = CommentService(db_session)
        comment = await service.create(
            content="Hey @admin and @manager please review",
            entity_type="contact",
            entity_id=test_contact.id,
            user_id=test_user.id,
        )
        assert "admin" in comment["mentions"]
        assert "manager" in comment["mentions"]

    @pytest.mark.asyncio
    async def test_update_comment(
        self,
        db_session: AsyncSession,
        test_user: User,
        test_contact: Contact,
    ):
        """Test updating a comment."""
        service = CommentService(db_session)
        created = await service.create("Original", "contact", test_contact.id, test_user.id)

        comment = await service.get_by_id(created["id"])
        updated = await service.update(comment, "Updated content")
        assert updated["content"] == "Updated content"

    @pytest.mark.asyncio
    async def test_delete_comment(
        self,
        db_session: AsyncSession,
        test_user: User,
        test_contact: Contact,
    ):
        """Test deleting a comment."""
        service = CommentService(db_session)
        created = await service.create("To delete", "contact", test_contact.id, test_user.id)

        comment = await service.get_by_id(created["id"])
        await service.delete(comment)

        deleted = await service.get_by_id(created["id"])
        assert deleted is None


class TestCommentEndpoints:
    """Tests for comment API endpoints."""

    @pytest.mark.asyncio
    async def test_list_comments_endpoint(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_comment: Comment,
        test_contact: Contact,
    ):
        """Test listing comments via API."""
        response = await client.get(
            "/api/comments",
            headers=auth_headers,
            params={
                "entity_type": "contacts",
                "entity_id": test_contact.id,
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert "total" in data
        assert data["total"] >= 1

    @pytest.mark.asyncio
    async def test_create_comment_endpoint(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_contact: Contact,
    ):
        """Test creating a comment via API."""
        response = await client.post(
            "/api/comments",
            headers=auth_headers,
            json={
                "content": "API comment test @admin",
                "entity_type": "contacts",
                "entity_id": test_contact.id,
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["content"] == "API comment test @admin"
        assert "admin" in data["mentions"]
        assert data["author_name"] is not None

    @pytest.mark.asyncio
    async def test_create_reply_endpoint(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_comment: Comment,
        test_contact: Contact,
    ):
        """Test creating a reply via API."""
        response = await client.post(
            "/api/comments",
            headers=auth_headers,
            json={
                "content": "Reply to comment",
                "entity_type": "contact",
                "entity_id": test_contact.id,
                "parent_id": test_comment.id,
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["parent_id"] == test_comment.id

    @pytest.mark.asyncio
    async def test_create_reply_invalid_parent(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_contact: Contact,
    ):
        """Test creating a reply with invalid parent ID."""
        response = await client.post(
            "/api/comments",
            headers=auth_headers,
            json={
                "content": "Reply to nothing",
                "entity_type": "contact",
                "entity_id": test_contact.id,
                "parent_id": 99999,
            },
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_create_internal_comment_endpoint(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_contact: Contact,
    ):
        """Test creating an internal comment via API."""
        response = await client.post(
            "/api/comments",
            headers=auth_headers,
            json={
                "content": "Internal note for team only",
                "entity_type": "contact",
                "entity_id": test_contact.id,
                "is_internal": True,
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["is_internal"] is True

    @pytest.mark.asyncio
    async def test_get_comment_endpoint(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_comment: Comment,
    ):
        """Test getting a single comment by ID."""
        response = await client.get(
            f"/api/comments/{test_comment.id}",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == test_comment.id

    @pytest.mark.asyncio
    async def test_get_comment_not_found(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
    ):
        """Test getting non-existent comment."""
        response = await client.get(
            "/api/comments/99999",
            headers=auth_headers,
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_update_comment_endpoint(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_comment: Comment,
    ):
        """Test updating a comment via API."""
        response = await client.patch(
            f"/api/comments/{test_comment.id}",
            headers=auth_headers,
            json={"content": "Updated comment content"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["content"] == "Updated comment content"

    @pytest.mark.asyncio
    async def test_update_comment_forbidden(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_contact: Contact,
    ):
        """Test that updating another user's comment is forbidden."""
        # Create a comment by a different user
        other_user = User(
            email="other@example.com",
            hashed_password="hash",
            full_name="Other User",
            is_active=True,
        )
        db_session.add(other_user)
        await db_session.commit()
        await db_session.refresh(other_user)

        comment = Comment(
            content="Other's comment",
            entity_type="contact",
            entity_id=test_contact.id,
            user_id=other_user.id,
        )
        db_session.add(comment)
        await db_session.commit()
        await db_session.refresh(comment)

        response = await client.patch(
            f"/api/comments/{comment.id}",
            headers=auth_headers,
            json={"content": "Trying to edit"},
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_delete_comment_endpoint(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_user: User,
        test_contact: Contact,
    ):
        """Test deleting a comment via API."""
        # Create comment to delete
        comment = Comment(
            content="To be deleted",
            entity_type="contact",
            entity_id=test_contact.id,
            user_id=test_user.id,
        )
        db_session.add(comment)
        await db_session.commit()
        await db_session.refresh(comment)
        cid = comment.id

        response = await client.delete(
            f"/api/comments/{cid}",
            headers=auth_headers,
        )
        assert response.status_code == 204

        # Verify deleted
        result = await db_session.execute(
            select(Comment).where(Comment.id == cid)
        )
        assert result.scalar_one_or_none() is None

    @pytest.mark.asyncio
    async def test_delete_comment_forbidden(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_contact: Contact,
    ):
        """Test that deleting another user's comment is forbidden."""
        other_user = User(
            email="deleteother@example.com",
            hashed_password="hash",
            full_name="Delete Other User",
            is_active=True,
        )
        db_session.add(other_user)
        await db_session.commit()
        await db_session.refresh(other_user)

        comment = Comment(
            content="Not yours",
            entity_type="contact",
            entity_id=test_contact.id,
            user_id=other_user.id,
        )
        db_session.add(comment)
        await db_session.commit()
        await db_session.refresh(comment)

        response = await client.delete(
            f"/api/comments/{comment.id}",
            headers=auth_headers,
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_comments_unauthorized(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ):
        """Test comment endpoints without authentication."""
        response = await client.get("/api/comments", params={"entity_type": "contact", "entity_id": 1})
        assert response.status_code == 401

        response = await client.post("/api/comments", json={"content": "test", "entity_type": "contact", "entity_id": 1})
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_comment_pagination(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_user: User,
        test_contact: Contact,
    ):
        """Test comment pagination."""
        # Create 15 comments
        for i in range(15):
            comment = Comment(
                content=f"Comment {i}",
                entity_type="contact",
                entity_id=test_contact.id,
                user_id=test_user.id,
            )
            db_session.add(comment)
        await db_session.commit()

        response = await client.get(
            "/api/comments",
            headers=auth_headers,
            params={
                "entity_type": "contact",
                "entity_id": test_contact.id,
                "page": 1,
                "page_size": 10,
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 10
        assert data["total"] == 15

        # Second page
        response = await client.get(
            "/api/comments",
            headers=auth_headers,
            params={
                "entity_type": "contact",
                "entity_id": test_contact.id,
                "page": 2,
                "page_size": 10,
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 5
