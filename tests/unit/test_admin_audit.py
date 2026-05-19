"""Tests for admin audit dashboard and work session tracking."""

from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from src.activities.models import Activity
from src.audit.models import AuditLog, WorkSession
from src.audit.service import WorkSessionService
from src.auth.models import User
from src.contacts.models import Contact


class TestAdminAuditAccess:
    @pytest.mark.asyncio
    async def test_summary_forbidden_for_regular_user(
        self,
        client: AsyncClient,
        auth_headers: dict,
    ):
        """Regular users cannot access admin audit summaries."""
        response = await client.get("/api/admin/audit/summary", headers=auth_headers)
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_summary_allowed_for_admin(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
    ):
        """Admins can access admin audit summaries."""
        response = await client.get("/api/admin/audit/summary", headers=admin_auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert "totals" in data
        assert "users" in data
        assert "entities" in data
        assert "security" in data


class TestAdminAuditFeed:
    @pytest.mark.asyncio
    async def test_feed_filters_and_user_email(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        admin_auth_headers: dict,
        test_user: User,
        test_admin_user: User,
    ):
        """Feed supports user/action/search filters and includes user email."""
        now = datetime(2026, 5, 18, 14, 0, tzinfo=UTC)
        db_session.add_all([
            AuditLog(
                entity_type="contact",
                entity_id=1,
                user_id=test_user.id,
                action="update",
                changes=[{"field": "stage", "old_value": "new", "new_value": "qualified"}],
                timestamp=now,
            ),
            AuditLog(
                entity_type="lead",
                entity_id=2,
                user_id=test_admin_user.id,
                action="delete",
                changes=None,
                timestamp=now + timedelta(minutes=1),
            ),
        ])
        await db_session.commit()

        response = await client.get(
            "/api/admin/audit/feed",
            headers=admin_auth_headers,
            params={
                "user_id": test_user.id,
                "action": "update",
                "search": "qualified",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["items"][0]["user_email"] == test_user.email
        assert data["items"][0]["action"] == "update"


class TestAdminAuditSummary:
    @pytest.mark.asyncio
    async def test_summary_aggregates_sessions_activities_and_audits(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        admin_auth_headers: dict,
        test_user: User,
        test_contact: Contact,
    ):
        """Summary combines estimated time, activities, audit counts, and entities."""
        now = datetime(2026, 5, 18, 15, 0, tzinfo=UTC)
        db_session.add_all([
            WorkSession(
                user_id=test_user.id,
                entity_type="contacts",
                entity_id=test_contact.id,
                started_at=now,
                last_seen_at=now + timedelta(minutes=2),
                duration_seconds=120,
                source="detail_page",
            ),
            Activity(
                activity_type="call",
                subject="Discovery call",
                entity_type="contacts",
                entity_id=test_contact.id,
                is_completed=True,
                call_duration_minutes=7,
                owner_id=test_user.id,
                created_by_id=test_user.id,
                created_at=now,
                updated_at=now,
            ),
            AuditLog(
                entity_type="proposal",
                entity_id=99,
                user_id=test_user.id,
                action="update",
                changes=[{"field": "status", "old_value": "draft", "new_value": "sent"}],
                timestamp=now,
            ),
        ])
        await db_session.commit()

        response = await client.get(
            "/api/admin/audit/summary",
            headers=admin_auth_headers,
            params={"start_date": "2026-05-18", "end_date": "2026-05-18"},
        )

        assert response.status_code == 200
        data = response.json()
        user_row = next(row for row in data["users"] if row["user_id"] == test_user.id)
        assert user_row["active_crm_seconds"] == 120
        assert user_row["calls"] == 1
        assert user_row["call_duration_minutes"] == 7
        assert user_row["proposals_touched"] == 1

        contact_row = next(
            row for row in data["entities"]
            if row["entity_type"] == "contacts" and row["entity_id"] == test_contact.id
        )
        assert contact_row["active_crm_seconds"] == 120
        assert contact_row["activity_count"] == 1


class TestWorkSessions:
    @pytest.mark.asyncio
    async def test_heartbeat_merges_until_idle_timeout(
        self,
        db_session: AsyncSession,
        test_user: User,
        test_contact: Contact,
    ):
        """Heartbeats merge while active and split after five idle minutes."""
        service = WorkSessionService(db_session)
        start = datetime(2026, 5, 18, 16, 0, tzinfo=UTC)

        first = await service.heartbeat(
            user_id=test_user.id,
            entity_type="contacts",
            entity_id=test_contact.id,
            now=start,
        )
        second = await service.heartbeat(
            user_id=test_user.id,
            entity_type="contact",
            entity_id=test_contact.id,
            now=start + timedelta(seconds=45),
        )
        third = await service.heartbeat(
            user_id=test_user.id,
            entity_type="contacts",
            entity_id=test_contact.id,
            now=start + timedelta(minutes=6),
        )

        assert second.id == first.id
        assert second.duration_seconds == 45
        assert third.id != first.id

        result = await db_session.execute(
            select(WorkSession).where(WorkSession.id == first.id)
        )
        closed = result.scalar_one()
        assert closed.ended_at is not None
        assert closed.duration_seconds == 45

    @pytest.mark.asyncio
    async def test_heartbeat_endpoint_records_current_user_session(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_user: User,
        test_contact: Contact,
    ):
        """Authenticated users can record their own visible-tab heartbeat."""
        response = await client.post(
            "/api/work-sessions/heartbeat",
            headers=auth_headers,
            json={
                "entity_type": "contacts",
                "entity_id": test_contact.id,
                "metadata": {"route": "/contacts/1"},
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["user_id"] == test_user.id
        assert data["entity_type"] == "contacts"

        result = await db_session.execute(select(WorkSession))
        assert result.scalar_one().metadata_ == {"route": "/contacts/1"}
