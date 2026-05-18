"""
Tests that verify notification creation is wired into entity routers.

Each test creates/updates an entity via the API and verifies the correct
notification was created in the database. No mocking is used; real database
records are checked.
"""

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from src.account.models import UserNotificationPrefs
from src.auth.models import User
from src.companies.models import Company
from src.contacts.models import Contact
from src.leads.models import Lead, LeadSource
from src.notifications.models import Notification
from src.opportunities.models import Opportunity, PipelineStage


async def _enable_all_notifications(db_session: AsyncSession, user: User) -> None:
    """Create a fully-opted-in prefs row — required under the opt-in gate."""
    prefs = UserNotificationPrefs(
        user_id=user.id,
        in_app_enabled=True,
        email_enabled=True,
        event_matrix={
            "lead_assigned": {"in_app": True, "email": True},
            "task_due": {"in_app": True, "email": True},
            "mention": {"in_app": True, "email": True},
        },
    )
    db_session.add(prefs)
    await db_session.flush()


class TestLeadAssignmentNotification:
    """Verify notifications are created when leads are assigned."""

    @pytest.mark.asyncio
    async def test_assigning_lead_to_another_user_creates_notification(
        self,
        client: AsyncClient,
        manager_auth_headers: dict,
        db_session: AsyncSession,
        test_user: User,
        test_lead_source: LeadSource,
    ):
        """Creating a lead assigned to a different user should notify that user.

        Uses manager_auth_headers because the lead-create gate added in
        the 2026-05-18 sharing-permissions PR refuses cross-user owner
        assignment for sales_rep accounts. The notification wiring
        itself is owner-agnostic — manager creds let us exercise it.
        """
        # Create a second user to assign to
        other_user = User(
            email="other@example.com",
            hashed_password="hashed",
            full_name="Other User",
            is_active=True,
        )
        db_session.add(other_user)
        await db_session.commit()
        await db_session.refresh(other_user)
        await _enable_all_notifications(db_session, other_user)

        response = await client.post(
            "/api/leads",
            headers=manager_auth_headers,
            json={
                "first_name": "Notify",
                "last_name": "Lead",
                "email": "notifylead@example.com",
                "status": "new",
                "source_id": test_lead_source.id,
                "owner_id": other_user.id,
            },
        )
        assert response.status_code == 201

        result = await db_session.execute(
            select(Notification).where(
                Notification.user_id == other_user.id,
                Notification.type == "assignment",
                Notification.entity_type == "leads",
            )
        )
        notifications = list(result.scalars().all())
        assert len(notifications) == 1
        assert "Notify Lead" in notifications[0].message

    @pytest.mark.asyncio
    async def test_updating_lead_owner_creates_notification(
        self,
        client: AsyncClient,
        manager_auth_headers: dict,
        db_session: AsyncSession,
        test_user: User,
        test_lead: Lead,
    ):
        """Changing lead owner should create a notification for the new owner.

        Uses manager_auth_headers — same rationale as the create test:
        cross-user reassignment is manager-gated as of 2026-05-18.
        """
        new_owner = User(
            email="newowner@example.com",
            hashed_password="hashed",
            full_name="New Owner",
            is_active=True,
        )
        db_session.add(new_owner)
        await db_session.commit()
        await db_session.refresh(new_owner)
        await _enable_all_notifications(db_session, new_owner)

        response = await client.patch(
            f"/api/leads/{test_lead.id}",
            headers=manager_auth_headers,
            json={"owner_id": new_owner.id},
        )
        assert response.status_code == 200

        result = await db_session.execute(
            select(Notification).where(
                Notification.user_id == new_owner.id,
                Notification.type == "assignment",
                Notification.entity_type == "leads",
            )
        )
        notifications = list(result.scalars().all())
        assert len(notifications) == 1

    @pytest.mark.asyncio
    async def test_updating_lead_without_owner_change_no_notification(
        self,
        client: AsyncClient,
        auth_headers: dict,
        db_session: AsyncSession,
        test_user: User,
        test_lead: Lead,
    ):
        """Updating a lead without changing owner should NOT create a notification."""
        response = await client.patch(
            f"/api/leads/{test_lead.id}",
            headers=auth_headers,
            json={"status": "contacted"},
        )
        assert response.status_code == 200

        result = await db_session.execute(
            select(Notification).where(
                Notification.type == "assignment",
                Notification.entity_type == "leads",
                Notification.entity_id == test_lead.id,
            )
        )
        notifications = list(result.scalars().all())
        assert len(notifications) == 0


class TestActivityDueNotification:
    """Verify notifications are created when activities with due dates are created."""

    @pytest.mark.asyncio
    async def test_creating_activity_with_due_date_creates_notification(
        self,
        client: AsyncClient,
        auth_headers: dict,
        db_session: AsyncSession,
        test_user: User,
        test_contact: Contact,
    ):
        """Creating an activity with a due_date should create an activity_due notification."""
        await _enable_all_notifications(db_session, test_user)

        response = await client.post(
            "/api/activities",
            headers=auth_headers,
            json={
                "activity_type": "task",
                "subject": "Follow up call",
                "entity_type": "contacts",
                "entity_id": test_contact.id,
                "due_date": "2026-03-15",
                "priority": "high",
            },
        )
        assert response.status_code == 201
        activity_id = response.json()["id"]

        result = await db_session.execute(
            select(Notification).where(
                Notification.type == "activity_due",
                Notification.entity_type == "activities",
                Notification.entity_id == activity_id,
            )
        )
        notifications = list(result.scalars().all())
        assert len(notifications) == 1
        assert "Follow up call" in notifications[0].message

    @pytest.mark.asyncio
    async def test_creating_activity_without_due_date_no_notification(
        self,
        client: AsyncClient,
        auth_headers: dict,
        db_session: AsyncSession,
        test_user: User,
        test_contact: Contact,
    ):
        """Creating an activity without a due_date should NOT create an activity_due notification."""
        response = await client.post(
            "/api/activities",
            headers=auth_headers,
            json={
                "activity_type": "note",
                "subject": "Quick note",
                "entity_type": "contacts",
                "entity_id": test_contact.id,
                "priority": "normal",
            },
        )
        assert response.status_code == 201

        result = await db_session.execute(
            select(Notification).where(
                Notification.type == "activity_due",
            )
        )
        notifications = list(result.scalars().all())
        assert len(notifications) == 0
