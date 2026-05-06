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
from src.opportunities.models import Opportunity


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
                # Missing subject
            },
        )

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_create_activity_without_entity(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_user: User,
    ):
        """Test creating activity without entity_type/entity_id defaults to user."""
        response = await client.post(
            "/api/activities",
            headers=auth_headers,
            json={
                "activity_type": "task",
                "subject": "Standalone task",
                "priority": "normal",
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert data["entity_type"] == "user"
        assert data["entity_id"] == test_user.id
        assert data["owner_id"] == test_user.id


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


class TestActivitiesCalendar:
    """Regression: PG rejects `date >= varchar` in the calendar range filter."""

    @pytest.mark.asyncio
    async def test_calendar_range_returns_activities(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_user: User,
        test_contact: Contact,
    ):
        """Test calendar filters activities by scheduled_at and due_date within range."""
        today = date.today()
        scheduled = Activity(
            activity_type="meeting",
            subject="In range (scheduled)",
            entity_type="contacts",
            entity_id=test_contact.id,
            scheduled_at=datetime.combine(today, datetime.min.time(), tzinfo=timezone.utc),
            owner_id=test_user.id,
            created_by_id=test_user.id,
        )
        due = Activity(
            activity_type="task",
            subject="In range (due)",
            entity_type="contacts",
            entity_id=test_contact.id,
            due_date=today + timedelta(days=1),
            owner_id=test_user.id,
            created_by_id=test_user.id,
        )
        out_of_range = Activity(
            activity_type="task",
            subject="Out of range",
            entity_type="contacts",
            entity_id=test_contact.id,
            due_date=today + timedelta(days=60),
            owner_id=test_user.id,
            created_by_id=test_user.id,
        )
        db_session.add_all([scheduled, due, out_of_range])
        await db_session.commit()

        start = today - timedelta(days=1)
        end = today + timedelta(days=7)
        response = await client.get(
            "/api/activities/calendar",
            headers=auth_headers,
            params={"start_date": start.isoformat(), "end_date": end.isoformat()},
        )

        assert response.status_code == 200, response.text
        subjects = {a["subject"] for day in response.json()["dates"].values() for a in day}
        assert "In range (scheduled)" in subjects
        assert "In range (due)" in subjects
        assert "Out of range" not in subjects


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


class TestActivitiesFilterByOwner:
    """Tests for filtering activities by owner_id."""

    @pytest.mark.asyncio
    async def test_list_activities_filter_by_owner(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_user: User,
        test_contact: Contact,
    ):
        """Test filtering activities by owner_id returns only owned activities."""
        # Create activities owned by test_user
        for i in range(3):
            activity = Activity(
                activity_type="call",
                subject=f"Owned Call {i}",
                entity_type="contacts",
                entity_id=test_contact.id,
                priority="normal",
                owner_id=test_user.id,
                created_by_id=test_user.id,
            )
            db_session.add(activity)
        await db_session.commit()

        response = await client.get(
            "/api/activities",
            headers=auth_headers,
            params={"owner_id": test_user.id},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["total"] >= 3
        assert all(a["owner_id"] == test_user.id for a in data["items"])


class TestActivitiesFilterByAssignee:
    """Tests for filtering activities by assigned_to_id."""

    @pytest.mark.asyncio
    async def test_list_activities_filter_by_assigned_to(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_user: User,
        test_superuser: User,
        test_contact: Contact,
    ):
        """Test filtering activities by assigned_to_id returns only assigned activities."""
        # Create activity assigned to superuser
        assigned_activity = Activity(
            activity_type="task",
            subject="Assigned to superuser",
            entity_type="contacts",
            entity_id=test_contact.id,
            priority="high",
            owner_id=test_user.id,
            assigned_to_id=test_superuser.id,
            created_by_id=test_user.id,
        )
        # Create activity assigned to test_user
        own_activity = Activity(
            activity_type="task",
            subject="Assigned to user",
            entity_type="contacts",
            entity_id=test_contact.id,
            priority="normal",
            owner_id=test_user.id,
            assigned_to_id=test_user.id,
            created_by_id=test_user.id,
        )
        db_session.add_all([assigned_activity, own_activity])
        await db_session.commit()

        response = await client.get(
            "/api/activities",
            headers=auth_headers,
            params={"assigned_to_id": test_superuser.id},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["total"] >= 1
        assert all(a["assigned_to_id"] == test_superuser.id for a in data["items"])


class TestMyTasksLimit:
    """Tests for my-tasks endpoint with limit parameter."""

    @pytest.mark.asyncio
    async def test_get_my_tasks_with_limit(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_user: User,
        test_contact: Contact,
    ):
        """Test getting tasks with a custom limit returns at most that many tasks."""
        # Create 5 task activities
        for i in range(5):
            task = Activity(
                activity_type="task",
                subject=f"Limited Task {i}",
                entity_type="contacts",
                entity_id=test_contact.id,
                priority="normal",
                is_completed=False,
                owner_id=test_user.id,
                created_by_id=test_user.id,
            )
            db_session.add(task)
        await db_session.commit()

        response = await client.get(
            "/api/activities/my-tasks",
            headers=auth_headers,
            params={"limit": 3},
        )

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) <= 3


class TestEntityTimelineFiltered:
    """Tests for entity timeline with activity_types filter."""

    @pytest.mark.asyncio
    async def test_get_entity_timeline_filter_by_activity_types(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_user: User,
        test_contact: Contact,
    ):
        """Test getting entity timeline filtered by activity types."""
        # Create activities of different types
        call = Activity(
            activity_type="call",
            subject="Timeline Call",
            entity_type="contacts",
            entity_id=test_contact.id,
            priority="normal",
            owner_id=test_user.id,
            created_by_id=test_user.id,
        )
        email = Activity(
            activity_type="email",
            subject="Timeline Email",
            entity_type="contacts",
            entity_id=test_contact.id,
            priority="normal",
            owner_id=test_user.id,
            created_by_id=test_user.id,
        )
        db_session.add_all([call, email])
        await db_session.commit()

        response = await client.get(
            f"/api/activities/timeline/entity/contacts/{test_contact.id}",
            headers=auth_headers,
            params={"activity_types": "call"},
        )

        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert isinstance(data["items"], list)


class TestUserTimelineOptions:
    """Tests for user timeline with include_assigned parameter."""

    @pytest.mark.asyncio
    async def test_get_user_timeline_exclude_assigned(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_activity: Activity,
    ):
        """Test getting user timeline with include_assigned=False."""
        response = await client.get(
            "/api/activities/timeline/user",
            headers=auth_headers,
            params={"include_assigned": False},
        )

        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert isinstance(data["items"], list)


class TestUpcomingActivitiesOptions:
    """Tests for upcoming activities with different days_ahead."""

    @pytest.mark.asyncio
    async def test_get_upcoming_activities_custom_days(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_user: User,
        test_contact: Contact,
    ):
        """Test getting upcoming activities with a longer lookahead window."""
        # Create activity scheduled 20 days from now
        from datetime import timezone
        far_activity = Activity(
            activity_type="meeting",
            subject="Far Future Meeting",
            entity_type="contacts",
            entity_id=test_contact.id,
            scheduled_at=datetime.now(timezone.utc) + timedelta(days=20),
            priority="normal",
            owner_id=test_user.id,
            created_by_id=test_user.id,
        )
        db_session.add(far_activity)
        await db_session.commit()

        response = await client.get(
            "/api/activities/upcoming",
            headers=auth_headers,
            params={"days_ahead": 30},
        )

        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert isinstance(data["items"], list)


class TestPersonalCalendarPrivacy:
    """Personal Google Calendar mirrors (entity_type='users') must be
    private to the user whose calendar they came from — admin/superuser
    role does NOT override. Regression for prod leak where an admin saw
    107 of another user's synced calendar events on /activities.
    """

    @pytest.mark.asyncio
    async def test_admin_does_not_see_other_users_calendar_mirror(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
        test_superuser: User,
    ):
        """Admin listing /api/activities does not see another user's calendar."""
        from src.auth.security import create_access_token

        # Calendar mirror created by Google Calendar sync for test_user
        # — entity_type='users', entity_id=test_user.id matches
        # google_calendar/service.py exactly.
        calendar_mirror = Activity(
            activity_type="meeting",
            subject="Private 1:1 with manager",
            entity_type="users",
            entity_id=test_user.id,
            scheduled_at=datetime.now(timezone.utc) + timedelta(days=1),
            priority="normal",
            is_completed=False,
            owner_id=test_user.id,
            created_by_id=test_user.id,
        )
        db_session.add(calendar_mirror)
        await db_session.commit()

        admin_token = create_access_token(data={"sub": str(test_superuser.id)})
        admin_headers = {"Authorization": f"Bearer {admin_token}"}

        response = await client.get("/api/activities", headers=admin_headers)

        assert response.status_code == 200
        data = response.json()
        assert all(a["id"] != calendar_mirror.id for a in data["items"]), (
            "Admin must not see another user's personal calendar mirror"
        )

    @pytest.mark.asyncio
    async def test_user_still_sees_own_calendar_mirror(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_user: User,
    ):
        """A user's own calendar mirror is still listed for them."""
        own_mirror = Activity(
            activity_type="meeting",
            subject="My Google Calendar event",
            entity_type="users",
            entity_id=test_user.id,
            scheduled_at=datetime.now(timezone.utc) + timedelta(days=1),
            priority="normal",
            is_completed=False,
            owner_id=test_user.id,
            created_by_id=test_user.id,
        )
        db_session.add(own_mirror)
        await db_session.commit()

        response = await client.get("/api/activities", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert any(a["id"] == own_mirror.id for a in data["items"])

    @pytest.mark.asyncio
    async def test_admin_calendar_view_does_not_pull_other_user(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
        test_superuser: User,
    ):
        """Admin passing ?owner_id=<other> to /calendar must not return
        that user's personal mirror — same invariant as the list endpoint.
        """
        from src.auth.security import create_access_token

        scheduled = datetime.now(timezone.utc) + timedelta(days=1)
        calendar_mirror = Activity(
            activity_type="meeting",
            subject="Other user's private event",
            entity_type="users",
            entity_id=test_user.id,
            scheduled_at=scheduled,
            priority="normal",
            is_completed=False,
            owner_id=test_user.id,
            created_by_id=test_user.id,
        )
        db_session.add(calendar_mirror)
        await db_session.commit()

        admin_token = create_access_token(data={"sub": str(test_superuser.id)})
        admin_headers = {"Authorization": f"Bearer {admin_token}"}

        start = (scheduled - timedelta(days=1)).date().isoformat()
        end = (scheduled + timedelta(days=1)).date().isoformat()

        response = await client.get(
            "/api/activities/calendar",
            headers=admin_headers,
            params={"start_date": start, "end_date": end, "owner_id": test_user.id},
        )

        assert response.status_code == 200
        data = response.json()
        all_ids = [
            item["id"]
            for date_items in data["dates"].values()
            for item in date_items
        ]
        assert calendar_mirror.id not in all_ids


class TestActivityContactPropagation:
    """Activities created against an opportunity copy the opportunity's
    contact_id onto the row so the contact's Activities tab can surface
    opportunity-driven rows without each caller writing two records."""

    @pytest.mark.asyncio
    async def test_activity_on_opportunity_carries_contact_id(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_opportunity: Opportunity,
        test_contact: Contact,
    ):
        response = await client.post(
            "/api/activities",
            headers=auth_headers,
            json={
                "activity_type": "call",
                "subject": "Discovery call on the deal",
                "entity_type": "opportunities",
                "entity_id": test_opportunity.id,
                "priority": "high",
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert data["entity_type"] == "opportunities"
        assert data["entity_id"] == test_opportunity.id
        # The opportunity fixture is bound to test_contact — the service
        # should mirror that onto the new activity.
        assert data["contact_id"] == test_contact.id

        # Verify the row was actually persisted with the FK populated.
        result = await db_session.execute(
            select(Activity).where(Activity.id == data["id"])
        )
        stored = result.scalar_one()
        assert stored.contact_id == test_contact.id

    @pytest.mark.asyncio
    async def test_activity_on_opportunity_without_contact_stays_null(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_opportunity: Opportunity,
    ):
        """An opportunity with no contact must not crash — contact_id stays null."""
        test_opportunity.contact_id = None
        await db_session.commit()

        response = await client.post(
            "/api/activities",
            headers=auth_headers,
            json={
                "activity_type": "task",
                "subject": "Internal prep",
                "entity_type": "opportunities",
                "entity_id": test_opportunity.id,
                "priority": "normal",
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert data["contact_id"] is None

    @pytest.mark.asyncio
    async def test_activity_on_contact_does_not_overwrite_explicit_contact_id(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_contact: Contact,
    ):
        """Creating against entity_type='contacts' shouldn't auto-populate
        contact_id from an opportunity lookup — it's only the
        opportunities path that mirrors."""
        response = await client.post(
            "/api/activities",
            headers=auth_headers,
            json={
                "activity_type": "note",
                "subject": "Random contact note",
                "entity_type": "contacts",
                "entity_id": test_contact.id,
                "priority": "normal",
            },
        )

        assert response.status_code == 201
        data = response.json()
        # Caller didn't pass contact_id and entity_type isn't opportunities,
        # so contact_id stays null even though entity_id matches a contact.
        assert data["contact_id"] is None
