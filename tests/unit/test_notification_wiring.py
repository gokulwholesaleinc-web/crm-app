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

from src.auth.models import User
from src.leads.models import Lead, LeadSource
from src.contacts.models import Contact
from src.companies.models import Company
from src.opportunities.models import Opportunity, PipelineStage
from src.notifications.models import Notification


class TestLeadAssignmentNotification:
    """Verify notifications are created when leads are assigned."""

    @pytest.mark.asyncio
    async def test_assigning_lead_to_another_user_creates_notification(
        self,
        client: AsyncClient,
        auth_headers: dict,
        db_session: AsyncSession,
        test_user: User,
        test_lead_source: LeadSource,
    ):
        """Creating a lead assigned to a different user should notify that user."""
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

        response = await client.post(
            "/api/leads",
            headers=auth_headers,
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
        auth_headers: dict,
        db_session: AsyncSession,
        test_user: User,
        test_lead: Lead,
    ):
        """Changing lead owner should create a notification for the new owner."""
        new_owner = User(
            email="newowner@example.com",
            hashed_password="hashed",
            full_name="New Owner",
            is_active=True,
        )
        db_session.add(new_owner)
        await db_session.commit()
        await db_session.refresh(new_owner)

        response = await client.patch(
            f"/api/leads/{test_lead.id}",
            headers=auth_headers,
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


class TestOpportunityStageChangeNotification:
    """Verify notifications are created when opportunity stages change."""

    @pytest.mark.asyncio
    async def test_changing_opportunity_stage_creates_notification(
        self,
        client: AsyncClient,
        auth_headers: dict,
        db_session: AsyncSession,
        test_opportunity: Opportunity,
        test_won_stage: PipelineStage,
    ):
        """Changing pipeline stage should create a stage_change notification."""
        response = await client.patch(
            f"/api/opportunities/{test_opportunity.id}",
            headers=auth_headers,
            json={"pipeline_stage_id": test_won_stage.id},
        )
        assert response.status_code == 200

        result = await db_session.execute(
            select(Notification).where(
                Notification.type == "stage_change",
                Notification.entity_type == "opportunities",
                Notification.entity_id == test_opportunity.id,
            )
        )
        notifications = list(result.scalars().all())
        assert len(notifications) == 1
        assert "Qualification" in notifications[0].message or "Closed Won" in notifications[0].message


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
