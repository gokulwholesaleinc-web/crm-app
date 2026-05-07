"""Tests for notifications API endpoints."""

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.models import User
from src.auth.security import create_access_token, get_password_hash
from src.notifications.event_handler import notification_event_handler
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


# ---------------------------------------------------------------------------
# Notifications wiring tests (audit findings)
# ---------------------------------------------------------------------------


async def _create_user(db_session: AsyncSession, email: str, is_superuser: bool = False) -> User:
    user = User(
        email=email,
        hashed_password=get_password_hash("password123"),
        full_name=email.split("@")[0],
        is_active=True,
        is_superuser=is_superuser,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


def _auth_headers_for(user: User) -> dict:
    token = create_access_token(data={"sub": str(user.id)})
    return {"Authorization": f"Bearer {token}"}


class TestActivityAssignmentNotifications:
    """Tests covering A and B: activity reassignment wiring."""

    @pytest.mark.asyncio
    async def test_activity_reassign_creates_notification_for_new_assignee(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_contact,
    ):
        """Reassigning an activity to a different user creates a notification for that user."""
        from datetime import datetime, timedelta, timezone

        user_a = await _create_user(db_session, "user_a_assign@example.com")
        user_b = await _create_user(db_session, "user_b_assign@example.com")

        activity_resp = await client.post(
            "/api/activities",
            json={
                "activity_type": "task",
                "subject": "Reassignment test",
                "entity_type": "contacts",
                "entity_id": test_contact.id,
                "assigned_to_id": user_a.id,
                "owner_id": user_a.id,
                "scheduled_at": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
            },
            headers=_auth_headers_for(user_a),
        )
        assert activity_resp.status_code == 201, activity_resp.text
        activity_id = activity_resp.json()["id"]

        # Count user_b assignment notifications before the PATCH
        before = await db_session.execute(
            select(Notification).where(
                Notification.user_id == user_b.id,
                Notification.type == "assignment",
            )
        )
        before_count = len(before.scalars().all())

        patch_resp = await client.patch(
            f"/api/activities/{activity_id}",
            json={"assigned_to_id": user_b.id},
            headers=_auth_headers_for(user_a),
        )
        assert patch_resp.status_code == 200, patch_resp.text

        result = await db_session.execute(
            select(Notification).where(
                Notification.user_id == user_b.id,
                Notification.type == "assignment",
                Notification.entity_type == "activities",
                Notification.entity_id == activity_id,
            )
        )
        new_notifs = result.scalars().all()
        assert len(new_notifs) == before_count + 1

    @pytest.mark.asyncio
    async def test_activity_reassign_no_notification_when_unchanged(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_contact,
    ):
        """PATCHing an activity without changing assigned_to_id creates no new assignment notification."""
        from datetime import datetime, timedelta, timezone

        user_a = await _create_user(db_session, "user_a_nochg@example.com")

        activity_resp = await client.post(
            "/api/activities",
            json={
                "activity_type": "task",
                "subject": "No change test",
                "entity_type": "contacts",
                "entity_id": test_contact.id,
                "assigned_to_id": user_a.id,
                "owner_id": user_a.id,
                "scheduled_at": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
            },
            headers=_auth_headers_for(user_a),
        )
        assert activity_resp.status_code == 201, activity_resp.text
        activity_id = activity_resp.json()["id"]

        before = await db_session.execute(
            select(Notification).where(
                Notification.user_id == user_a.id,
                Notification.type == "assignment",
            )
        )
        before_count = len(before.scalars().all())

        patch_resp = await client.patch(
            f"/api/activities/{activity_id}",
            json={"subject": "Updated subject only"},
            headers=_auth_headers_for(user_a),
        )
        assert patch_resp.status_code == 200, patch_resp.text

        after = await db_session.execute(
            select(Notification).where(
                Notification.user_id == user_a.id,
                Notification.type == "assignment",
            )
        )
        after_count = len(after.scalars().all())
        assert after_count == before_count


class TestQuoteRejectNotification:
    """Test C: quote.rejected emits event and notifies owner."""

    @pytest.mark.asyncio
    async def test_quote_reject_emits_event_and_notifies_owner(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_contact,
    ):
        """Rejecting a quote in 'sent' status creates a quote_rejected notification for the owner."""
        user_a = await _create_user(db_session, "quote_owner_reject@example.com")

        create_resp = await client.post(
            "/api/quotes",
            json={
                "title": "Quote to reject",
                "contact_id": test_contact.id,
                "owner_id": user_a.id,
                "status": "draft",
            },
            headers=_auth_headers_for(user_a),
        )
        assert create_resp.status_code == 201, create_resp.text
        quote_id = create_resp.json()["id"]

        # Move to 'sent' via the service directly in DB
        from src.quotes.models import Quote
        quote = await db_session.get(Quote, quote_id)
        from datetime import datetime, timezone
        quote.status = "sent"
        quote.sent_at = datetime.now(timezone.utc)
        await db_session.commit()

        reject_resp = await client.post(
            f"/api/quotes/{quote_id}/reject",
            headers=_auth_headers_for(user_a),
        )
        assert reject_resp.status_code == 200, reject_resp.text
        assert reject_resp.json()["status"] == "rejected"

        result = await db_session.execute(
            select(Notification).where(
                Notification.user_id == user_a.id,
                Notification.type == "quote_rejected",
            )
        )
        notifs = result.scalars().all()
        assert len(notifs) == 1
        assert "reject" in notifs[0].title.lower() or "quote" in notifs[0].title.lower()


class TestProposalRejectNotification:
    """Test D: proposal.rejected emits event and notifies owner."""

    @pytest.mark.asyncio
    async def test_proposal_reject_emits_event_and_notifies_owner(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ):
        """Rejecting a proposal in 'sent' status creates a proposal_rejected notification for the owner."""
        from datetime import datetime, timezone

        user_a = await _create_user(db_session, "proposal_owner_reject@example.com")

        create_resp = await client.post(
            "/api/proposals",
            json={
                "title": "Proposal to reject",
                "owner_id": user_a.id,
                "status": "draft",
            },
            headers=_auth_headers_for(user_a),
        )
        assert create_resp.status_code == 201, create_resp.text
        proposal_id = create_resp.json()["id"]

        from src.proposals.models import Proposal
        proposal = await db_session.get(Proposal, proposal_id)
        proposal.status = "sent"
        proposal.sent_at = datetime.now(timezone.utc)
        await db_session.commit()

        reject_resp = await client.post(
            f"/api/proposals/{proposal_id}/reject",
            headers=_auth_headers_for(user_a),
        )
        assert reject_resp.status_code == 200, reject_resp.text
        assert reject_resp.json()["status"] == "rejected"

        result = await db_session.execute(
            select(Notification).where(
                Notification.user_id == user_a.id,
                Notification.type == "proposal_rejected",
            )
        )
        notifs = result.scalars().all()
        assert len(notifs) == 1
        assert "reject" in notifs[0].title.lower() or "proposal" in notifs[0].title.lower()


class TestQuoteSentNotifiesOwner:
    """Test E: quote.sent routes notification to owner, not the actor."""

    @pytest.mark.asyncio
    async def test_quote_sent_notifies_owner_not_actor(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_contact,
    ):
        """Sending a quote as admin notifies the quote's owner (user_a), not the acting admin."""
        user_a = await _create_user(db_session, "quote_owner_send@example.com")
        admin_b = await _create_user(db_session, "admin_actor_send@example.com", is_superuser=True)

        create_resp = await client.post(
            "/api/quotes",
            json={
                "title": "Quote to send",
                "contact_id": test_contact.id,
                "owner_id": user_a.id,
                "status": "draft",
            },
            headers=_auth_headers_for(user_a),
        )
        assert create_resp.status_code == 201, create_resp.text
        quote_id = create_resp.json()["id"]

        send_resp = await client.post(
            f"/api/quotes/{quote_id}/send",
            headers=_auth_headers_for(admin_b),
        )
        assert send_resp.status_code == 200, send_resp.text
        assert send_resp.json()["status"] == "sent"

        # Owner (user_a) gets a quote_sent notification
        owner_notifs = await db_session.execute(
            select(Notification).where(
                Notification.user_id == user_a.id,
                Notification.type == "quote_sent",
            )
        )
        assert len(owner_notifs.scalars().all()) == 1

        # Actor (admin_b) does NOT get a quote_sent notification
        actor_notifs = await db_session.execute(
            select(Notification).where(
                Notification.user_id == admin_b.id,
                Notification.type == "quote_sent",
            )
        )
        assert len(actor_notifs.scalars().all()) == 0


class TestProposalSentNotifiesOwner:
    """Test F: proposal.sent routes notification to owner, not the actor."""

    @pytest.mark.asyncio
    async def test_proposal_sent_notifies_owner_not_actor(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_contact,
    ):
        """Sending a proposal as admin notifies the proposal's owner (user_a), not the acting admin."""
        user_a = await _create_user(db_session, "proposal_owner_send@example.com")
        admin_b = await _create_user(db_session, "admin_actor_proposal@example.com", is_superuser=True)

        create_resp = await client.post(
            "/api/proposals",
            json={
                "title": "Proposal to send",
                "contact_id": test_contact.id,
                "owner_id": user_a.id,
                "status": "draft",
            },
            headers=_auth_headers_for(user_a),
        )
        assert create_resp.status_code == 201, create_resp.text
        proposal_id = create_resp.json()["id"]

        send_resp = await client.post(
            f"/api/proposals/{proposal_id}/send",
            headers=_auth_headers_for(admin_b),
        )
        assert send_resp.status_code == 200, send_resp.text
        assert send_resp.json()["status"] == "sent"

        # Owner (user_a) gets a proposal_sent notification
        owner_notifs = await db_session.execute(
            select(Notification).where(
                Notification.user_id == user_a.id,
                Notification.type == "proposal_sent",
            )
        )
        assert len(owner_notifs.scalars().all()) == 1

        # Actor (admin_b) does NOT get a proposal_sent notification
        actor_notifs = await db_session.execute(
            select(Notification).where(
                Notification.user_id == admin_b.id,
                Notification.type == "proposal_sent",
            )
        )
        assert len(actor_notifs.scalars().all()) == 0


class TestPaymentReceivedNotification:
    """Tests G and H: payment.received notification routing."""

    @pytest.mark.asyncio
    async def test_payment_received_notification_routes_to_quote_owner(
        self,
        db_session: AsyncSession,
    ):
        """payment.received handler creates a notification for the user specified in payload."""
        user_a = await _create_user(db_session, "payment_owner_notif@example.com")

        payload = {
            "entity_id": 9001,
            "entity_type": "payment",
            "user_id": user_a.id,
            "data": {
                "event_type": "checkout.session.completed",
                "event_id": "evt_test_001",
                "quote_id": None,
                "opportunity_id": None,
            },
        }
        await notification_event_handler("payment.received", payload)

        result = await db_session.execute(
            select(Notification).where(
                Notification.user_id == user_a.id,
                Notification.type == "payment_received",
            )
        )
        notifs = result.scalars().all()
        assert len(notifs) == 1
        assert notifs[0].entity_id == 9001
        assert notifs[0].entity_type == "payment"

    @pytest.mark.asyncio
    async def test_payment_received_no_owner_warns_and_drops(
        self,
        db_session: AsyncSession,
    ):
        """payment.received handler with no user_id creates no notification row."""
        before = await db_session.execute(
            select(Notification).where(Notification.type == "payment_received")
        )
        before_count = len(before.scalars().all())

        payload = {
            "entity_id": None,
            "entity_type": "payment",
            "user_id": None,
            "data": {
                "event_type": "invoice.paid",
                "event_id": "evt_test_no_owner",
                "quote_id": None,
                "opportunity_id": None,
            },
        }
        await notification_event_handler("payment.received", payload)

        after = await db_session.execute(
            select(Notification).where(Notification.type == "payment_received")
        )
        after_count = len(after.scalars().all())
        assert after_count == before_count
