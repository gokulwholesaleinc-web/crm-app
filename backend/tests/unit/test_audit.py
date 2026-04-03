"""
Unit tests for audit log endpoints.

Tests for recording and retrieving entity change history.
"""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.models import User
from src.contacts.models import Contact
from src.companies.models import Company
from src.opportunities.models import Opportunity, PipelineStage
from src.audit.models import AuditLog
from src.audit.service import AuditService, detect_changes


class TestAuditService:
    """Tests for the audit service layer."""

    @pytest.mark.asyncio
    async def test_log_change_create(
        self,
        db_session: AsyncSession,
        test_user: User,
    ):
        """Test logging a create action."""
        service = AuditService(db_session)
        entry = await service.log_change(
            entity_type="contact",
            entity_id=1,
            user_id=test_user.id,
            action="create",
        )
        assert entry.id is not None
        assert entry.action == "create"
        assert entry.entity_type == "contact"
        assert entry.entity_id == 1
        assert entry.user_id == test_user.id

    @pytest.mark.asyncio
    async def test_log_change_update_with_changes(
        self,
        db_session: AsyncSession,
        test_user: User,
    ):
        """Test logging an update action with field changes."""
        service = AuditService(db_session)
        changes = [
            {"field": "name", "old_value": "Old Name", "new_value": "New Name"},
            {"field": "amount", "old_value": 10000, "new_value": 20000},
        ]
        entry = await service.log_change(
            entity_type="opportunity",
            entity_id=1,
            user_id=test_user.id,
            action="update",
            changes=changes,
        )
        assert entry.action == "update"
        assert entry.changes is not None
        assert len(entry.changes) == 2
        assert entry.changes[0]["field"] == "name"

    @pytest.mark.asyncio
    async def test_log_change_delete(
        self,
        db_session: AsyncSession,
        test_user: User,
    ):
        """Test logging a delete action."""
        service = AuditService(db_session)
        entry = await service.log_change(
            entity_type="lead",
            entity_id=5,
            user_id=test_user.id,
            action="delete",
        )
        assert entry.action == "delete"
        assert entry.entity_id == 5

    @pytest.mark.asyncio
    async def test_get_entity_history(
        self,
        db_session: AsyncSession,
        test_user: User,
    ):
        """Test retrieving audit history for an entity."""
        service = AuditService(db_session)

        # Create multiple audit entries
        await service.log_change("contact", 10, test_user.id, "create")
        await service.log_change("contact", 10, test_user.id, "update",
                                 changes=[{"field": "email", "old_value": "a@b.com", "new_value": "c@d.com"}])
        await service.log_change("contact", 10, test_user.id, "update",
                                 changes=[{"field": "phone", "old_value": "111", "new_value": "222"}])

        items, total = await service.get_entity_history("contact", 10)
        assert total == 3
        assert len(items) == 3
        # Most recent first
        assert items[0]["action"] == "update"

    @pytest.mark.asyncio
    async def test_get_entity_history_pagination(
        self,
        db_session: AsyncSession,
        test_user: User,
    ):
        """Test paginated audit history."""
        service = AuditService(db_session)

        for i in range(15):
            await service.log_change("company", 1, test_user.id, "update")

        items, total = await service.get_entity_history("company", 1, page=1, page_size=10)
        assert total == 15
        assert len(items) == 10

        items2, _ = await service.get_entity_history("company", 1, page=2, page_size=10)
        assert len(items2) == 5

    @pytest.mark.asyncio
    async def test_get_entity_history_empty(
        self,
        db_session: AsyncSession,
    ):
        """Test audit history for entity with no changes."""
        service = AuditService(db_session)
        items, total = await service.get_entity_history("contact", 999)
        assert total == 0
        assert len(items) == 0

    @pytest.mark.asyncio
    async def test_get_entity_history_includes_user_name(
        self,
        db_session: AsyncSession,
        test_user: User,
    ):
        """Test audit history includes user name."""
        service = AuditService(db_session)
        await service.log_change("contact", 1, test_user.id, "create")

        items, _ = await service.get_entity_history("contact", 1)
        assert len(items) == 1
        assert items[0]["user_name"] == test_user.full_name


class TestDetectChanges:
    """Tests for the detect_changes utility function."""

    def test_detect_changes_with_differences(self):
        """Test detecting changes between two dicts."""
        old = {"name": "Old", "amount": 100, "status": "open"}
        new = {"name": "New", "amount": 200, "status": "open"}
        changes = detect_changes(old, new)
        assert len(changes) == 2
        fields = {c["field"] for c in changes}
        assert "name" in fields
        assert "amount" in fields

    def test_detect_changes_no_differences(self):
        """Test detect_changes when values are identical."""
        old = {"name": "Same", "amount": 100}
        new = {"name": "Same", "amount": 100}
        changes = detect_changes(old, new)
        assert len(changes) == 0

    def test_detect_changes_with_none_values(self):
        """Test detect_changes handling None values."""
        old = {"name": "Test", "phone": None}
        new = {"name": "Test", "phone": "+1-555-0100"}
        changes = detect_changes(old, new)
        assert len(changes) == 1
        assert changes[0]["field"] == "phone"
        assert changes[0]["old_value"] is None

    def test_detect_changes_date_values(self):
        """Test detect_changes with date values."""
        from datetime import date
        old = {"close_date": date(2025, 1, 1)}
        new = {"close_date": date(2025, 6, 15)}
        changes = detect_changes(old, new)
        assert len(changes) == 1


class TestAuditEndpoint:
    """Tests for the audit log API endpoint."""

    @pytest.mark.asyncio
    async def test_get_audit_log(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_user: User,
    ):
        """Test getting audit log for an entity via API."""
        # Create audit entries directly
        service = AuditService(db_session)
        await service.log_change("contact", 1, test_user.id, "create")
        await db_session.commit()

        response = await client.get(
            "/api/audit/contact/1",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert "total" in data
        assert data["total"] >= 1

    @pytest.mark.asyncio
    async def test_get_audit_log_pagination(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_user: User,
    ):
        """Test paginated audit log endpoint."""
        service = AuditService(db_session)
        for i in range(15):
            await service.log_change("opportunity", 5, test_user.id, "update")
        await db_session.commit()

        response = await client.get(
            "/api/audit/opportunity/5",
            headers=auth_headers,
            params={"page": 1, "page_size": 10},
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 10
        assert data["total"] == 15

    @pytest.mark.asyncio
    async def test_get_audit_log_empty(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
    ):
        """Test audit log for entity with no history."""
        response = await client.get(
            "/api/audit/contact/999",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 0
        assert data["items"] == []

    @pytest.mark.asyncio
    async def test_get_audit_log_unauthorized(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ):
        """Test audit log without authentication."""
        response = await client.get("/api/audit/contact/1")
        assert response.status_code == 401


class TestAuditIntegration:
    """Tests that audit logging is triggered by CRUD operations."""

    @pytest.mark.asyncio
    async def test_contact_create_generates_audit(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_company: Company,
    ):
        """Test that creating a contact generates an audit entry."""
        response = await client.post(
            "/api/contacts",
            headers=auth_headers,
            json={
                "first_name": "Audit",
                "last_name": "Test",
                "email": "audit.test@example.com",
                "company_id": test_company.id,
                "status": "active",
            },
        )
        assert response.status_code == 201
        contact_id = response.json()["id"]

        # Check audit log
        audit_response = await client.get(
            f"/api/audit/contact/{contact_id}",
            headers=auth_headers,
        )
        assert audit_response.status_code == 200
        data = audit_response.json()
        assert data["total"] >= 1
        assert any(item["action"] == "create" for item in data["items"])

    @pytest.mark.asyncio
    async def test_contact_update_generates_audit(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_contact: Contact,
    ):
        """Test that updating a contact generates an audit entry."""
        response = await client.patch(
            f"/api/contacts/{test_contact.id}",
            headers=auth_headers,
            json={"first_name": "UpdatedName"},
        )
        assert response.status_code == 200

        audit_response = await client.get(
            f"/api/audit/contact/{test_contact.id}",
            headers=auth_headers,
        )
        assert audit_response.status_code == 200
        data = audit_response.json()
        assert any(item["action"] == "update" for item in data["items"])

    @pytest.mark.asyncio
    async def test_opportunity_create_generates_audit(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_pipeline_stage: PipelineStage,
    ):
        """Test that creating an opportunity generates an audit entry."""
        response = await client.post(
            "/api/opportunities",
            headers=auth_headers,
            json={
                "name": "Audit Opportunity Test",
                "pipeline_stage_id": test_pipeline_stage.id,
                "amount": 50000,
            },
        )
        assert response.status_code == 201
        opp_id = response.json()["id"]

        audit_response = await client.get(
            f"/api/audit/opportunity/{opp_id}",
            headers=auth_headers,
        )
        assert audit_response.status_code == 200
        data = audit_response.json()
        assert data["total"] >= 1
        assert any(item["action"] == "create" for item in data["items"])
