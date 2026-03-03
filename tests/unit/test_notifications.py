"""Tests for notifications API endpoints."""

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.notifications.models import Notification


class TestListNotifications:
    """Tests for GET /api/notifications."""

    @pytest.mark.asyncio
    async def test_list_empty(self, client: AsyncClient, auth_headers: dict):
        """Should return empty list with zero total when no notifications exist."""
        response = await client.get("/api/notifications", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["items"] == []
        assert data["total"] == 0

    @pytest.mark.asyncio
    async def test_list_requires_auth(self, client: AsyncClient):
        """Should return 401 when listing notifications without authentication."""
        response = await client.get("/api/notifications")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_list_shows_user_notifications(
        self,
        client: AsyncClient,
        auth_headers: dict,
        db_session: AsyncSession,
        test_user,
    ):
        """Should return the user's own notifications in the list."""
        notif = Notification(
            user_id=test_user.id,
            type="test",
            title="Test notification",
            message="Hello world",
        )
        db_session.add(notif)
        await db_session.flush()

        response = await client.get("/api/notifications", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["items"][0]["title"] == "Test notification"

    @pytest.mark.asyncio
    async def test_list_does_not_show_other_user_notifications(
        self,
        client: AsyncClient,
        auth_headers: dict,
        db_session: AsyncSession,
    ):
        """Should not show notifications belonging to other users."""
        # Create notification for a different user (id=9999)
        notif = Notification(
            user_id=9999,
            type="test",
            title="Other user notif",
            message="Should not see this",
        )
        db_session.add(notif)
        await db_session.flush()

        response = await client.get("/api/notifications", headers=auth_headers)
        assert response.status_code == 200
        assert response.json()["total"] == 0


class TestUnreadCount:
    """Tests for GET /api/notifications/unread-count."""

    @pytest.mark.asyncio
    async def test_unread_count_zero(
        self, client: AsyncClient, auth_headers: dict
    ):
        """Should return zero unread count when no notifications exist."""
        response = await client.get(
            "/api/notifications/unread-count", headers=auth_headers
        )
        assert response.status_code == 200
        assert response.json()["count"] == 0

    @pytest.mark.asyncio
    async def test_unread_count_with_notifications(
        self,
        client: AsyncClient,
        auth_headers: dict,
        db_session: AsyncSession,
        test_user,
    ):
        """Should return correct unread count when unread notifications exist."""
        for i in range(3):
            notif = Notification(
                user_id=test_user.id,
                type="test",
                title=f"Notif {i}",
                message=f"Message {i}",
            )
            db_session.add(notif)
        await db_session.flush()

        response = await client.get(
            "/api/notifications/unread-count", headers=auth_headers
        )
        assert response.status_code == 200
        assert response.json()["count"] == 3

    @pytest.mark.asyncio
    async def test_unread_count_requires_auth(self, client: AsyncClient):
        """Should return 401 when checking unread count without authentication."""
        response = await client.get("/api/notifications/unread-count")
        assert response.status_code == 401


class TestMarkRead:
    """Tests for PUT /api/notifications/{id}/read."""

    @pytest.mark.asyncio
    async def test_mark_read(
        self,
        client: AsyncClient,
        auth_headers: dict,
        db_session: AsyncSession,
        test_user,
    ):
        """Should mark a notification as read and return is_read true."""
        notif = Notification(
            user_id=test_user.id,
            type="test",
            title="Mark read test",
            message="Should be read",
        )
        db_session.add(notif)
        await db_session.flush()

        response = await client.put(
            f"/api/notifications/{notif.id}/read", headers=auth_headers
        )
        assert response.status_code == 200
        assert response.json()["is_read"] is True

    @pytest.mark.asyncio
    async def test_mark_read_decrements_unread_count(
        self,
        client: AsyncClient,
        auth_headers: dict,
        db_session: AsyncSession,
        test_user,
    ):
        """Should decrement unread count to zero after marking the only notification as read."""
        notif = Notification(
            user_id=test_user.id,
            type="test",
            title="Count test",
            message="Msg",
        )
        db_session.add(notif)
        await db_session.flush()

        # Mark as read
        await client.put(
            f"/api/notifications/{notif.id}/read", headers=auth_headers
        )

        # Check unread count is 0
        response = await client.get(
            "/api/notifications/unread-count", headers=auth_headers
        )
        assert response.json()["count"] == 0

    @pytest.mark.asyncio
    async def test_mark_read_not_found(
        self, client: AsyncClient, auth_headers: dict
    ):
        """Should return 404 when marking a non-existent notification as read."""
        response = await client.put(
            "/api/notifications/99999/read", headers=auth_headers
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_mark_read_requires_auth(self, client: AsyncClient):
        """Should return 401 when marking as read without authentication."""
        response = await client.put("/api/notifications/1/read")
        assert response.status_code == 401


class TestMarkAllRead:
    """Tests for PUT /api/notifications/read-all."""

    @pytest.mark.asyncio
    async def test_mark_all_read(
        self,
        client: AsyncClient,
        auth_headers: dict,
        db_session: AsyncSession,
        test_user,
    ):
        """Should mark all unread notifications as read and return updated count."""
        for i in range(3):
            notif = Notification(
                user_id=test_user.id,
                type="test",
                title=f"Notif {i}",
                message=f"Msg {i}",
            )
            db_session.add(notif)
        await db_session.flush()

        response = await client.put(
            "/api/notifications/read-all", headers=auth_headers
        )
        assert response.status_code == 200
        assert response.json()["updated"] == 3

        # Verify all are read
        count_resp = await client.get(
            "/api/notifications/unread-count", headers=auth_headers
        )
        assert count_resp.json()["count"] == 0

    @pytest.mark.asyncio
    async def test_mark_all_read_when_none(
        self, client: AsyncClient, auth_headers: dict
    ):
        """Should return updated count of zero when no unread notifications exist."""
        response = await client.put(
            "/api/notifications/read-all", headers=auth_headers
        )
        assert response.status_code == 200
        assert response.json()["updated"] == 0

    @pytest.mark.asyncio
    async def test_mark_all_read_requires_auth(self, client: AsyncClient):
        """Should return 401 when marking all as read without authentication."""
        response = await client.put("/api/notifications/read-all")
        assert response.status_code == 401


class TestDeleteNotification:
    """Tests for DELETE /api/notifications/{id}."""

    @pytest.mark.asyncio
    async def test_delete_notification(
        self,
        client: AsyncClient,
        auth_headers: dict,
        db_session: AsyncSession,
        test_user,
    ):
        """Should delete a single notification and return deleted true."""
        notif = Notification(
            user_id=test_user.id,
            type="test",
            title="Delete me",
            message="Should be deleted",
        )
        db_session.add(notif)
        await db_session.flush()

        response = await client.delete(
            f"/api/notifications/{notif.id}", headers=auth_headers
        )
        assert response.status_code == 200
        assert response.json()["deleted"] is True

        # Verify it's gone
        list_resp = await client.get("/api/notifications", headers=auth_headers)
        assert list_resp.json()["total"] == 0

    @pytest.mark.asyncio
    async def test_delete_notification_not_found(
        self, client: AsyncClient, auth_headers: dict
    ):
        """Should return 404 when deleting a non-existent notification."""
        response = await client.delete(
            "/api/notifications/99999", headers=auth_headers
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_notification_requires_auth(self, client: AsyncClient):
        """Should return 401 when deleting without authentication."""
        response = await client.delete("/api/notifications/1")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_delete_notification_updates_unread_count(
        self,
        client: AsyncClient,
        auth_headers: dict,
        db_session: AsyncSession,
        test_user,
    ):
        """Should decrement unread count when an unread notification is deleted."""
        notif = Notification(
            user_id=test_user.id,
            type="test",
            title="Unread to delete",
            message="Msg",
        )
        db_session.add(notif)
        await db_session.flush()

        await client.delete(f"/api/notifications/{notif.id}", headers=auth_headers)

        count_resp = await client.get(
            "/api/notifications/unread-count", headers=auth_headers
        )
        assert count_resp.json()["count"] == 0


class TestDeleteAllNotifications:
    """Tests for DELETE /api/notifications."""

    @pytest.mark.asyncio
    async def test_delete_all_notifications(
        self,
        client: AsyncClient,
        auth_headers: dict,
        db_session: AsyncSession,
        test_user,
    ):
        """Should delete all notifications and return deleted count."""
        for i in range(3):
            db_session.add(Notification(
                user_id=test_user.id,
                type="test",
                title=f"Notif {i}",
                message=f"Msg {i}",
            ))
        await db_session.flush()

        response = await client.delete("/api/notifications", headers=auth_headers)
        assert response.status_code == 200
        assert response.json()["deleted"] == 3

        # Verify all gone
        list_resp = await client.get("/api/notifications", headers=auth_headers)
        assert list_resp.json()["total"] == 0

    @pytest.mark.asyncio
    async def test_delete_all_when_none(
        self, client: AsyncClient, auth_headers: dict
    ):
        """Should return deleted count of zero when no notifications exist."""
        response = await client.delete("/api/notifications", headers=auth_headers)
        assert response.status_code == 200
        assert response.json()["deleted"] == 0

    @pytest.mark.asyncio
    async def test_delete_all_requires_auth(self, client: AsyncClient):
        """Should return 401 when clearing all notifications without authentication."""
        response = await client.delete("/api/notifications")
        assert response.status_code == 401


class TestNotificationWithEntity:
    """Tests for notifications with entity links."""

    @pytest.mark.asyncio
    async def test_notification_with_entity_link(
        self,
        client: AsyncClient,
        auth_headers: dict,
        db_session: AsyncSession,
        test_user,
        test_contact,
    ):
        """Should include entity_type and entity_id when notification is linked to an entity."""
        notif = Notification(
            user_id=test_user.id,
            type="assignment",
            title="Contact assigned",
            message="You were assigned a contact",
            entity_type="contacts",
            entity_id=test_contact.id,
        )
        db_session.add(notif)
        await db_session.flush()

        response = await client.get("/api/notifications", headers=auth_headers)
        assert response.status_code == 200
        item = response.json()["items"][0]
        assert item["entity_type"] == "contacts"
        assert item["entity_id"] == test_contact.id
