"""
Unit tests for data scoping and isolation between users.

Validates that notes, exports, reports, and admin endpoints
properly scope data to the current user.
"""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.models import User
from src.auth.security import get_password_hash, create_access_token
from src.contacts.models import Contact
from src.companies.models import Company
from src.leads.models import Lead, LeadSource
from src.core.models import Note


class TestNotesDataScoping:
    """Tests that notes list only returns notes created by the current user."""

    @pytest.mark.asyncio
    async def test_notes_list_scoped_to_current_user(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
        auth_headers: dict,
    ):
        """Create notes for two users and verify each only sees their own."""
        # Create a second user
        user2 = User(
            email="user2@example.com",
            hashed_password=get_password_hash("password123"),
            full_name="Second User",
            is_active=True,
            is_superuser=False,
        )
        db_session.add(user2)
        await db_session.commit()
        await db_session.refresh(user2)

        # Create notes for test_user (user 1)
        note1 = Note(
            content="Note by user 1",
            entity_type="contact",
            entity_id=1,
            created_by_id=test_user.id,
        )
        # Create notes for user 2
        note2 = Note(
            content="Note by user 2",
            entity_type="contact",
            entity_id=1,
            created_by_id=user2.id,
        )
        db_session.add_all([note1, note2])
        await db_session.commit()

        # User 1 should only see their own notes
        response = await client.get("/api/notes", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["total"] >= 1
        for item in data["items"]:
            assert item["created_by_id"] == test_user.id

    @pytest.mark.asyncio
    async def test_second_user_only_sees_own_notes(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
        test_contact: Contact,
    ):
        """Verify second user sees only their notes, not user 1's."""
        # Create a second user
        user2 = User(
            email="user2@example.com",
            hashed_password=get_password_hash("password123"),
            full_name="Second User",
            is_active=True,
            is_superuser=False,
        )
        db_session.add(user2)
        await db_session.commit()
        await db_session.refresh(user2)

        user2_token = create_access_token(data={"sub": str(user2.id)})
        user2_headers = {"Authorization": f"Bearer {user2_token}"}

        # Create notes for both users
        note1 = Note(
            content="Note by user 1",
            entity_type="contact",
            entity_id=test_contact.id,
            created_by_id=test_user.id,
        )
        note2 = Note(
            content="Note by user 2",
            entity_type="contact",
            entity_id=test_contact.id,
            created_by_id=user2.id,
        )
        db_session.add_all([note1, note2])
        await db_session.commit()

        # User 2 should only see their own notes
        response = await client.get("/api/notes", headers=user2_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["total"] >= 1
        for item in data["items"]:
            assert item["created_by_id"] == user2.id


class TestExportDataScoping:
    """Tests that CSV exports only return records owned by the current user."""

    @pytest.mark.asyncio
    async def test_export_contacts_scoped_to_user(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
        auth_headers: dict,
    ):
        """Export contacts returns only records owned by the current user."""
        # Create a second user
        user2 = User(
            email="user2@example.com",
            hashed_password=get_password_hash("password123"),
            full_name="Second User",
            is_active=True,
            is_superuser=False,
        )
        db_session.add(user2)
        await db_session.commit()
        await db_session.refresh(user2)

        # Create a contact owned by user 1
        contact1 = Contact(
            first_name="Alice",
            last_name="One",
            email="alice@example.com",
            status="active",
            owner_id=test_user.id,
            created_by_id=test_user.id,
        )
        # Create a contact owned by user 2
        contact2 = Contact(
            first_name="Bob",
            last_name="Two",
            email="bob@example.com",
            status="active",
            owner_id=user2.id,
            created_by_id=user2.id,
        )
        db_session.add_all([contact1, contact2])
        await db_session.commit()

        # Export as user 1 - should only contain user 1's contact
        response = await client.get(
            "/api/import-export/export/contacts",
            headers=auth_headers,
        )
        assert response.status_code == 200
        csv_content = response.text
        assert "Alice" in csv_content
        assert "Bob" not in csv_content

    @pytest.mark.asyncio
    async def test_export_companies_scoped_to_user(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
        auth_headers: dict,
    ):
        """Export companies returns only records owned by the current user."""
        user2 = User(
            email="user2@example.com",
            hashed_password=get_password_hash("password123"),
            full_name="Second User",
            is_active=True,
            is_superuser=False,
        )
        db_session.add(user2)
        await db_session.commit()
        await db_session.refresh(user2)

        company1 = Company(
            name="User1 Corp",
            status="prospect",
            owner_id=test_user.id,
            created_by_id=test_user.id,
        )
        company2 = Company(
            name="User2 Corp",
            status="prospect",
            owner_id=user2.id,
            created_by_id=user2.id,
        )
        db_session.add_all([company1, company2])
        await db_session.commit()

        response = await client.get(
            "/api/import-export/export/companies",
            headers=auth_headers,
        )
        assert response.status_code == 200
        csv_content = response.text
        assert "User1 Corp" in csv_content
        assert "User2 Corp" not in csv_content

    @pytest.mark.asyncio
    async def test_export_leads_scoped_to_user(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
        auth_headers: dict,
    ):
        """Export leads returns only records owned by the current user."""
        user2 = User(
            email="user2@example.com",
            hashed_password=get_password_hash("password123"),
            full_name="Second User",
            is_active=True,
            is_superuser=False,
        )
        db_session.add(user2)
        await db_session.commit()
        await db_session.refresh(user2)

        lead1 = Lead(
            first_name="Lead",
            last_name="One",
            email="lead1@example.com",
            status="new",
            owner_id=test_user.id,
            created_by_id=test_user.id,
        )
        lead2 = Lead(
            first_name="Lead",
            last_name="Two",
            email="lead2@example.com",
            status="new",
            owner_id=user2.id,
            created_by_id=user2.id,
        )
        db_session.add_all([lead1, lead2])
        await db_session.commit()

        response = await client.get(
            "/api/import-export/export/leads",
            headers=auth_headers,
        )
        assert response.status_code == 200
        csv_content = response.text
        assert "lead1@example.com" in csv_content
        assert "lead2@example.com" not in csv_content


class TestDebugDataScopeCheck:
    """Tests for the /api/debug/data-scope-check endpoint."""

    @pytest.mark.asyncio
    async def test_data_scope_check_returns_expected_structure(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
        auth_headers: dict,
    ):
        """Verify /api/debug/data-scope-check returns 200 with expected keys."""
        response = await client.get(
            "/api/debug/data-scope-check",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert "current_user_id" in data
        assert "current_user_email" in data
        assert "users" in data
        assert "records_by_owner" in data
        assert data["current_user_id"] == test_user.id
        assert data["current_user_email"] == test_user.email

    @pytest.mark.asyncio
    async def test_data_scope_check_unauthorized(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ):
        """Verify /api/debug/data-scope-check returns 401 without auth."""
        response = await client.get("/api/debug/data-scope-check")
        assert response.status_code == 401


@pytest.mark.skip(reason="/api/admin/reseed-demo-data endpoint not yet implemented")
class TestReseedDemoDataAccess:
    """Tests for the /api/admin/reseed-demo-data endpoint."""

    @pytest.mark.asyncio
    async def test_reseed_demo_data_forbidden_for_non_superuser(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
        auth_headers: dict,
    ):
        """Non-superuser should get 403 when calling reseed-demo-data."""
        response = await client.post(
            "/api/admin/reseed-demo-data",
            headers=auth_headers,
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_reseed_demo_data_unauthorized(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ):
        """Unauthenticated request should get 401."""
        response = await client.post("/api/admin/reseed-demo-data")
        assert response.status_code == 401


class TestReportExecuteScoping:
    """Tests that report execution scopes results to the current user."""

    @pytest.mark.asyncio
    async def test_report_execute_scopes_to_current_user(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
        auth_headers: dict,
    ):
        """Report count should only include records owned by the current user."""
        # Create a second user
        user2 = User(
            email="user2@example.com",
            hashed_password=get_password_hash("password123"),
            full_name="Second User",
            is_active=True,
            is_superuser=False,
        )
        db_session.add(user2)
        await db_session.commit()
        await db_session.refresh(user2)

        # Create contacts owned by different users
        contact1 = Contact(
            first_name="Report",
            last_name="User1",
            email="report1@example.com",
            status="active",
            owner_id=test_user.id,
            created_by_id=test_user.id,
        )
        contact2 = Contact(
            first_name="Report",
            last_name="User2",
            email="report2@example.com",
            status="active",
            owner_id=user2.id,
            created_by_id=user2.id,
        )
        db_session.add_all([contact1, contact2])
        await db_session.commit()

        # Execute report as user 1
        response = await client.post(
            "/api/reports/execute",
            headers=auth_headers,
            json={
                "entity_type": "contacts",
                "metric": "count",
                "chart_type": "bar",
            },
        )
        assert response.status_code == 200
        data = response.json()
        # Total should only count user 1's contacts
        assert data["total"] == 1

    @pytest.mark.asyncio
    async def test_report_execute_different_user_sees_own_data(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
    ):
        """Each user's report should reflect only their own records."""
        # Create a second user
        user2 = User(
            email="user2@example.com",
            hashed_password=get_password_hash("password123"),
            full_name="Second User",
            is_active=True,
            is_superuser=False,
        )
        db_session.add(user2)
        await db_session.commit()
        await db_session.refresh(user2)

        user2_token = create_access_token(data={"sub": str(user2.id)})
        user2_headers = {"Authorization": f"Bearer {user2_token}"}

        # Create 1 lead for user 1 and 2 leads for user 2
        lead1 = Lead(
            first_name="U1Lead",
            last_name="One",
            email="u1lead@example.com",
            status="new",
            owner_id=test_user.id,
            created_by_id=test_user.id,
        )
        lead2 = Lead(
            first_name="U2Lead",
            last_name="One",
            email="u2lead1@example.com",
            status="new",
            owner_id=user2.id,
            created_by_id=user2.id,
        )
        lead3 = Lead(
            first_name="U2Lead",
            last_name="Two",
            email="u2lead2@example.com",
            status="new",
            owner_id=user2.id,
            created_by_id=user2.id,
        )
        db_session.add_all([lead1, lead2, lead3])
        await db_session.commit()

        # User 2 report should count only their 2 leads
        response = await client.post(
            "/api/reports/execute",
            headers=user2_headers,
            json={
                "entity_type": "leads",
                "metric": "count",
                "chart_type": "bar",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 2
