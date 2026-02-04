"""
Unit tests for activities CRUD endpoints.

Tests for list, create, get, update, delete, and activity-specific operations.
"""

import pytest
from datetime import datetime, date, timedelta, timezone
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from src.auth.models import User
from src.activities.models import Activity
from src.contacts.models import Contact
from src.leads.models import Lead


class TestActivitiesList:
    """Tests for activities list endpoint with pagination."""

    @pytest.mark.asyncio
    async def test_list_activities_empty(
        self, client: AsyncClient, db_session: AsyncSession, auth_headers: dict
    ):
        """Test listing activities when none exist."""
        response = await client.get("/api/activities", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["items"] == []
        assert data["total"] == 0
        assert data["page"] == 1

    @pytest.mark.asyncio
    async def test_list_activities_with_data(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_activity: Activity,
    ):
        """Test listing activities with existing data."""
        response = await client.get("/api/activities", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["total"] >= 1
        assert len(data["items"]) >= 1
        assert any(a["id"] == test_activity.id for a in data["items"])

    @pytest.mark.asyncio
    async def test_list_activities_pagination(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_user: User,
        test_contact: Contact,
    ):
        """Test activities pagination."""
        # Create multiple activities
        for i in range(15):
            activity = Activity(
                activity_type="task",
                subject=f"Task {i}",
                entity_type="contacts",
                entity_id=test_contact.id,
                priority="normal",
                owner_id=test_user.id,
                created_by_id=test_user.id,
            )
            db_session.add(activity)
        await db_session.commit()

        # First page
        response = await client.get(
            "/api/activities",
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
            "/api/activities",
            headers=auth_headers,
            params={"page": 2, "page_size": 10},
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) >= 5

    @pytest.mark.asyncio
    async def test_list_activities_filter_by_type(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_activity: Activity,
    ):
        """Test filtering activities by type."""
        response = await client.get(
            "/api/activities",
            headers=auth_headers,
            params={"activity_type": "call"},
        )

        assert response.status_code == 200
        data = response.json()
        assert all(a["activity_type"] == "call" for a in data["items"])

    @pytest.mark.asyncio
    async def test_list_activities_filter_by_entity(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_activity: Activity,
        test_contact: Contact,
    ):
        """Test filtering activities by entity type and ID."""
        response = await client.get(
            "/api/activities",
            headers=auth_headers,
            params={
                "entity_type": "contacts",
                "entity_id": test_contact.id,
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert all(
            a["entity_type"] == "contacts" and a["entity_id"] == test_contact.id
            for a in data["items"]
        )

    @pytest.mark.asyncio
    async def test_list_activities_filter_by_completed(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_activity: Activity,
    ):
        """Test filtering activities by completion status."""
        response = await client.get(
            "/api/activities",
            headers=auth_headers,
            params={"is_completed": False},
        )

        assert response.status_code == 200
        data = response.json()
        assert all(a["is_completed"] is False for a in data["items"])

    @pytest.mark.asyncio
    async def test_list_activities_filter_by_priority(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_activity: Activity,
    ):
        """Test filtering activities by priority."""
        response = await client.get(
            "/api/activities",
            headers=auth_headers,
            params={"priority": "normal"},
        )

        assert response.status_code == 200
        data = response.json()
        assert all(a["priority"] == "normal" for a in data["items"])


class TestActivitiesCreate:
    """Tests for activity creation endpoint."""

    @pytest.mark.asyncio
    async def test_create_call_activity(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_contact: Contact,
    ):
        """Test creating a call activity."""
        response = await client.post(
            "/api/activities",
            headers=auth_headers,
            json={
                "activity_type": "call",
                "subject": "Introduction call",
                "description": "Initial introduction and discovery",
                "entity_type": "contacts",
                "entity_id": test_contact.id,
                "scheduled_at": (
                    datetime.now(timezone.utc) + timedelta(hours=2)
                ).isoformat(),
                "priority": "high",
                "call_duration_minutes": 30,
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert data["activity_type"] == "call"
        assert data["subject"] == "Introduction call"
        assert data["entity_type"] == "contacts"
        assert data["entity_id"] == test_contact.id
        assert data["priority"] == "high"
        assert data["is_completed"] is False

    @pytest.mark.asyncio
    async def test_create_email_activity(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_contact: Contact,
    ):
        """Test creating an email activity."""
        response = await client.post(
            "/api/activities",
            headers=auth_headers,
            json={
                "activity_type": "email",
                "subject": "Proposal follow-up",
                "description": "Sending proposal document",
                "entity_type": "contacts",
                "entity_id": test_contact.id,
                "email_to": "client@example.com",
                "email_cc": "manager@example.com",
                "priority": "normal",
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert data["activity_type"] == "email"
        assert data["email_to"] == "client@example.com"
        assert data["email_cc"] == "manager@example.com"

    @pytest.mark.asyncio
    async def test_create_meeting_activity(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_contact: Contact,
    ):
        """Test creating a meeting activity."""
        scheduled = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
        response = await client.post(
            "/api/activities",
            headers=auth_headers,
            json={
                "activity_type": "meeting",
                "subject": "Product demo",
                "description": "Demonstrating product features",
                "entity_type": "contacts",
                "entity_id": test_contact.id,
                "scheduled_at": scheduled,
                "meeting_location": "Conference Room A",
                "meeting_attendees": '[{"name": "John", "email": "john@example.com"}]',
                "priority": "high",
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert data["activity_type"] == "meeting"
        assert data["meeting_location"] == "Conference Room A"

    @pytest.mark.asyncio
    async def test_create_task_activity(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_contact: Contact,
        test_user: User,
    ):
        """Test creating a task activity."""
        due = (date.today() + timedelta(days=3)).isoformat()
        response = await client.post(
            "/api/activities",
            headers=auth_headers,
            json={
                "activity_type": "task",
                "subject": "Prepare proposal",
                "description": "Create and send proposal document",
                "entity_type": "contacts",
                "entity_id": test_contact.id,
                "due_date": due,
                "priority": "urgent",
                "assigned_to_id": test_user.id,
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert data["activity_type"] == "task"
        assert data["due_date"] == due
        assert data["priority"] == "urgent"

    @pytest.mark.asyncio
    async def test_create_note_activity(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_contact: Contact,
    ):
        """Test creating a note activity."""
        response = await client.post(
            "/api/activities",
            headers=auth_headers,
            json={
                "activity_type": "note",
                "subject": "Meeting notes",
                "description": "Detailed notes from our last meeting",
                "entity_type": "contacts",
                "entity_id": test_contact.id,
                "priority": "low",
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert data["activity_type"] == "note"

    @pytest.mark.asyncio
    async def test_create_activity_for_lead(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_lead: Lead,
    ):
        """Test creating activity for a lead entity."""
        response = await client.post(
            "/api/activities",
            headers=auth_headers,
            json={
                "activity_type": "call",
                "subject": "Lead qualification call",
                "entity_type": "leads",
                "entity_id": test_lead.id,
                "priority": "high",
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert data["entity_type"] == "leads"
        assert data["entity_id"] == test_lead.id

    @pytest.mark.asyncio
    async def test_create_activity_missing_required_fields(
        self, client: AsyncClient, db_session: AsyncSession, auth_headers: dict
    ):
        """Test creating activity without required fields fails."""
        response = await client.post(
            "/api/activities",
            headers=auth_headers,
            json={
                "activity_type": "call",
                # Missing subject, entity_type, entity_id
            },
        )

        assert response.status_code == 422


class TestActivitiesGetById:
    """Tests for get activity by ID endpoint."""

    @pytest.mark.asyncio
    async def test_get_activity_success(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_activity: Activity,
    ):
        """Test getting activity by ID."""
        response = await client.get(
            f"/api/activities/{test_activity.id}",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == test_activity.id
        assert data["subject"] == test_activity.subject
        assert data["activity_type"] == test_activity.activity_type

    @pytest.mark.asyncio
    async def test_get_activity_not_found(
        self, client: AsyncClient, db_session: AsyncSession, auth_headers: dict
    ):
        """Test getting non-existent activity."""
        response = await client.get(
            "/api/activities/99999",
            headers=auth_headers,
        )

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()


class TestActivitiesUpdate:
    """Tests for activity update endpoint."""

    @pytest.mark.asyncio
    async def test_update_activity_success(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_activity: Activity,
    ):
        """Test updating activity."""
        response = await client.patch(
            f"/api/activities/{test_activity.id}",
            headers=auth_headers,
            json={
                "subject": "Updated call subject",
                "description": "Updated description",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["subject"] == "Updated call subject"
        assert data["description"] == "Updated description"

    @pytest.mark.asyncio
    async def test_update_activity_not_found(
        self, client: AsyncClient, db_session: AsyncSession, auth_headers: dict
    ):
        """Test updating non-existent activity."""
        response = await client.patch(
            "/api/activities/99999",
            headers=auth_headers,
            json={"subject": "Test"},
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_update_activity_priority(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_activity: Activity,
    ):
        """Test updating activity priority."""
        response = await client.patch(
            f"/api/activities/{test_activity.id}",
            headers=auth_headers,
            json={"priority": "urgent"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["priority"] == "urgent"

    @pytest.mark.asyncio
    async def test_update_activity_scheduled_time(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_activity: Activity,
    ):
        """Test updating activity scheduled time."""
        new_time = (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()
        response = await client.patch(
            f"/api/activities/{test_activity.id}",
            headers=auth_headers,
            json={"scheduled_at": new_time},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["scheduled_at"] is not None

    @pytest.mark.asyncio
    async def test_update_activity_assignee(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_activity: Activity,
        test_superuser: User,
    ):
        """Test updating activity assignee."""
        response = await client.patch(
            f"/api/activities/{test_activity.id}",
            headers=auth_headers,
            json={"assigned_to_id": test_superuser.id},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["assigned_to_id"] == test_superuser.id


class TestActivitiesComplete:
    """Tests for completing activities."""

    @pytest.mark.asyncio
    async def test_complete_activity_success(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_activity: Activity,
    ):
        """Test completing an activity."""
        response = await client.post(
            f"/api/activities/{test_activity.id}/complete",
            headers=auth_headers,
            json={"notes": "Call completed successfully"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["is_completed"] is True
        assert data["completed_at"] is not None

    @pytest.mark.asyncio
    async def test_complete_activity_without_notes(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_user: User,
        test_contact: Contact,
    ):
        """Test completing an activity without notes."""
        # Create a new activity to complete
        activity = Activity(
            activity_type="task",
            subject="Task to complete",
            entity_type="contacts",
            entity_id=test_contact.id,
            priority="normal",
            owner_id=test_user.id,
            created_by_id=test_user.id,
        )
        db_session.add(activity)
        await db_session.commit()
        await db_session.refresh(activity)

        response = await client.post(
            f"/api/activities/{activity.id}/complete",
            headers=auth_headers,
            json={},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["is_completed"] is True

    @pytest.mark.asyncio
    async def test_complete_activity_not_found(
        self, client: AsyncClient, db_session: AsyncSession, auth_headers: dict
    ):
        """Test completing non-existent activity."""
        response = await client.post(
            "/api/activities/99999/complete",
            headers=auth_headers,
            json={},
        )

        assert response.status_code == 404


class TestActivitiesDelete:
    """Tests for activity delete endpoint."""

    @pytest.mark.asyncio
    async def test_delete_activity_success(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_user: User,
        test_contact: Contact,
    ):
        """Test deleting activity."""
        # Create an activity to delete
        activity = Activity(
            activity_type="task",
            subject="To Delete Task",
            entity_type="contacts",
            entity_id=test_contact.id,
            priority="low",
            owner_id=test_user.id,
            created_by_id=test_user.id,
        )
        db_session.add(activity)
        await db_session.commit()
        await db_session.refresh(activity)
        activity_id = activity.id

        response = await client.delete(
            f"/api/activities/{activity_id}",
            headers=auth_headers,
        )

        assert response.status_code == 204

        # Verify deletion
        result = await db_session.execute(
            select(Activity).where(Activity.id == activity_id)
        )
        deleted_activity = result.scalar_one_or_none()
        assert deleted_activity is None

    @pytest.mark.asyncio
    async def test_delete_activity_not_found(
        self, client: AsyncClient, db_session: AsyncSession, auth_headers: dict
    ):
        """Test deleting non-existent activity."""
        response = await client.delete(
            "/api/activities/99999",
            headers=auth_headers,
        )

        assert response.status_code == 404


class TestMyTasks:
    """Tests for getting user's tasks."""

    @pytest.mark.asyncio
    async def test_get_my_tasks(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_activity: Activity,
        test_user: User,
    ):
        """Test getting tasks for current user."""
        response = await client.get(
            "/api/activities/my-tasks",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    @pytest.mark.asyncio
    async def test_get_my_tasks_exclude_completed(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_user: User,
        test_contact: Contact,
    ):
        """Test getting tasks excluding completed ones."""
        # Create a completed task
        completed_task = Activity(
            activity_type="task",
            subject="Completed Task",
            entity_type="contacts",
            entity_id=test_contact.id,
            is_completed=True,
            completed_at=datetime.now(timezone.utc),
            owner_id=test_user.id,
            created_by_id=test_user.id,
        )
        db_session.add(completed_task)
        await db_session.commit()

        response = await client.get(
            "/api/activities/my-tasks",
            headers=auth_headers,
            params={"include_completed": False},
        )

        assert response.status_code == 200
        data = response.json()
        assert all(t["is_completed"] is False for t in data)


class TestActivityTimeline:
    """Tests for activity timeline endpoints."""

    @pytest.mark.asyncio
    async def test_get_entity_timeline(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_activity: Activity,
        test_contact: Contact,
    ):
        """Test getting timeline for an entity."""
        response = await client.get(
            f"/api/activities/timeline/entity/contacts/{test_contact.id}",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert isinstance(data["items"], list)

    @pytest.mark.asyncio
    async def test_get_user_timeline(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_activity: Activity,
    ):
        """Test getting timeline for current user."""
        response = await client.get(
            "/api/activities/timeline/user",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert "items" in data

    @pytest.mark.asyncio
    async def test_get_upcoming_activities(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_activity: Activity,
    ):
        """Test getting upcoming activities."""
        response = await client.get(
            "/api/activities/upcoming",
            headers=auth_headers,
            params={"days_ahead": 7},
        )

        assert response.status_code == 200
        data = response.json()
        assert "items" in data

    @pytest.mark.asyncio
    async def test_get_overdue_activities(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_user: User,
        test_contact: Contact,
    ):
        """Test getting overdue activities."""
        # Create an overdue task
        overdue_task = Activity(
            activity_type="task",
            subject="Overdue Task",
            entity_type="contacts",
            entity_id=test_contact.id,
            due_date=date.today() - timedelta(days=2),
            is_completed=False,
            owner_id=test_user.id,
            created_by_id=test_user.id,
        )
        db_session.add(overdue_task)
        await db_session.commit()

        response = await client.get(
            "/api/activities/overdue",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert "items" in data


class TestActivitiesUnauthorized:
    """Tests for unauthorized access to activities endpoints."""

    @pytest.mark.asyncio
    async def test_list_activities_unauthorized(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Test listing activities without auth fails."""
        response = await client.get("/api/activities")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_create_activity_unauthorized(
        self, client: AsyncClient, db_session: AsyncSession, test_contact: Contact
    ):
        """Test creating activity without auth fails."""
        response = await client.post(
            "/api/activities",
            json={
                "activity_type": "call",
                "subject": "Test",
                "entity_type": "contacts",
                "entity_id": test_contact.id,
            },
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_get_activity_unauthorized(
        self, client: AsyncClient, db_session: AsyncSession, test_activity: Activity
    ):
        """Test getting activity without auth fails."""
        response = await client.get(f"/api/activities/{test_activity.id}")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_update_activity_unauthorized(
        self, client: AsyncClient, db_session: AsyncSession, test_activity: Activity
    ):
        """Test updating activity without auth fails."""
        response = await client.patch(
            f"/api/activities/{test_activity.id}",
            json={"subject": "Hacked"},
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_delete_activity_unauthorized(
        self, client: AsyncClient, db_session: AsyncSession, test_activity: Activity
    ):
        """Test deleting activity without auth fails."""
        response = await client.delete(f"/api/activities/{test_activity.id}")
        assert response.status_code == 401
