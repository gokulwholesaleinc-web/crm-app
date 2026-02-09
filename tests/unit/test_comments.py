"""Tests for comment endpoints."""

import pytest


class TestCommentList:
    """Tests for GET /api/comments/{entity_type}/{entity_id}."""

    @pytest.mark.asyncio
    async def test_list_comments_empty(self, client, auth_headers):
        """Should return empty list when no comments exist."""
        response = await client.get(
            "/api/comments/contacts/999",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["items"] == []
        assert data["total"] == 0

    @pytest.mark.asyncio
    async def test_list_comments_with_entries(
        self, client, auth_headers, test_comment, test_contact
    ):
        """Should return comments for an entity."""
        response = await client.get(
            f"/api/comments/contact/{test_contact.id}",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["items"][0]["content"] == "This is a test comment"

    @pytest.mark.asyncio
    async def test_list_comments_pagination(
        self, client, auth_headers, db_session, test_user, test_contact
    ):
        """Should paginate comments."""
        from src.comments.models import Comment

        for i in range(15):
            c = Comment(
                content=f"Comment {i}",
                entity_type="contact",
                entity_id=test_contact.id,
                user_id=test_user.id,
                user_name=test_user.full_name,
            )
            db_session.add(c)
        await db_session.commit()

        response = await client.get(
            f"/api/comments/contact/{test_contact.id}?page=1&page_size=10",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 10
        assert data["total"] == 15
        assert data["pages"] == 2

    @pytest.mark.asyncio
    async def test_list_comments_requires_auth(self, client):
        """Should require authentication."""
        response = await client.get("/api/comments/contacts/1")
        assert response.status_code == 401


class TestCommentCreate:
    """Tests for POST /api/comments."""

    @pytest.mark.asyncio
    async def test_create_comment(self, client, auth_headers, test_contact):
        """Should create a comment successfully."""
        response = await client.post(
            "/api/comments",
            headers=auth_headers,
            json={
                "content": "New comment on contact",
                "entity_type": "contact",
                "entity_id": test_contact.id,
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["content"] == "New comment on contact"
        assert data["entity_type"] == "contact"
        assert data["entity_id"] == test_contact.id
        assert data["parent_id"] is None
        assert data["is_internal"] is False

    @pytest.mark.asyncio
    async def test_create_internal_comment(self, client, auth_headers, test_contact):
        """Should create an internal comment."""
        response = await client.post(
            "/api/comments",
            headers=auth_headers,
            json={
                "content": "Internal note",
                "entity_type": "contact",
                "entity_id": test_contact.id,
                "is_internal": True,
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["is_internal"] is True

    @pytest.mark.asyncio
    async def test_create_reply_comment(
        self, client, auth_headers, test_comment, test_contact
    ):
        """Should create a reply to an existing comment."""
        response = await client.post(
            "/api/comments",
            headers=auth_headers,
            json={
                "content": "This is a reply",
                "entity_type": "contact",
                "entity_id": test_contact.id,
                "parent_id": test_comment.id,
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["parent_id"] == test_comment.id

    @pytest.mark.asyncio
    async def test_create_comment_with_mentions(
        self, client, auth_headers, test_contact
    ):
        """Should extract @mentions from content."""
        response = await client.post(
            "/api/comments",
            headers=auth_headers,
            json={
                "content": "Hey @john.doe and @jane.smith please review",
                "entity_type": "contact",
                "entity_id": test_contact.id,
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert "john.doe" in data["mentioned_users"]
        assert "jane.smith" in data["mentioned_users"]

    @pytest.mark.asyncio
    async def test_create_comment_requires_auth(self, client, test_contact):
        """Should require authentication."""
        response = await client.post(
            "/api/comments",
            json={
                "content": "Unauthorized comment",
                "entity_type": "contact",
                "entity_id": test_contact.id,
            },
        )
        assert response.status_code == 401


class TestCommentUpdate:
    """Tests for PATCH /api/comments/{comment_id}."""

    @pytest.mark.asyncio
    async def test_update_own_comment(self, client, auth_headers, test_comment):
        """Should update own comment."""
        response = await client.patch(
            f"/api/comments/{test_comment.id}",
            headers=auth_headers,
            json={"content": "Updated comment content"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["content"] == "Updated comment content"

    @pytest.mark.asyncio
    async def test_update_other_users_comment_forbidden(
        self, client, db_session, auth_headers, test_contact
    ):
        """Should not allow updating another user's comment."""
        from src.comments.models import Comment

        other_comment = Comment(
            content="Other user comment",
            entity_type="contact",
            entity_id=test_contact.id,
            user_id=99999,
            user_name="Other User",
        )
        db_session.add(other_comment)
        await db_session.commit()
        await db_session.refresh(other_comment)

        response = await client.patch(
            f"/api/comments/{other_comment.id}",
            headers=auth_headers,
            json={"content": "Trying to edit"},
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_update_nonexistent_comment(self, client, auth_headers):
        """Should return 404 for nonexistent comment."""
        response = await client.patch(
            "/api/comments/99999",
            headers=auth_headers,
            json={"content": "Update nonexistent"},
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_update_comment_requires_auth(self, client):
        """Should require authentication."""
        response = await client.patch(
            "/api/comments/1",
            json={"content": "Unauthorized update"},
        )
        assert response.status_code == 401


class TestCommentDelete:
    """Tests for DELETE /api/comments/{comment_id}."""

    @pytest.mark.asyncio
    async def test_delete_own_comment(self, client, auth_headers, test_comment):
        """Should delete own comment."""
        response = await client.delete(
            f"/api/comments/{test_comment.id}",
            headers=auth_headers,
        )
        assert response.status_code == 204

    @pytest.mark.asyncio
    async def test_delete_other_users_comment_forbidden(
        self, client, db_session, auth_headers, test_contact
    ):
        """Should not allow deleting another user's comment."""
        from src.comments.models import Comment

        other_comment = Comment(
            content="Other user comment",
            entity_type="contact",
            entity_id=test_contact.id,
            user_id=99999,
            user_name="Other User",
        )
        db_session.add(other_comment)
        await db_session.commit()
        await db_session.refresh(other_comment)

        response = await client.delete(
            f"/api/comments/{other_comment.id}",
            headers=auth_headers,
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_delete_nonexistent_comment(self, client, auth_headers):
        """Should return 404 for nonexistent comment."""
        response = await client.delete(
            "/api/comments/99999",
            headers=auth_headers,
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_comment_requires_auth(self, client):
        """Should require authentication."""
        response = await client.delete("/api/comments/1")
        assert response.status_code == 401
