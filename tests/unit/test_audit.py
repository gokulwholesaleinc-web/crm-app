"""Tests for audit log endpoints."""

import json
import pytest
from datetime import datetime, timezone


class TestAuditLogGet:
    """Tests for GET /api/audit/{entity_type}/{entity_id}."""

    @pytest.mark.asyncio
    async def test_get_audit_log_empty(self, client, auth_headers):
        """Should return empty list when no audit entries exist."""
        response = await client.get(
            "/api/audit/contacts/999",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["items"] == []
        assert data["total"] == 0
        assert data["page"] == 1

    @pytest.mark.asyncio
    async def test_get_audit_log_with_entries(
        self, client, auth_headers, db_session, test_user, test_contact
    ):
        """Should return audit log entries for an entity."""
        from src.audit.models import AuditLog

        entry = AuditLog(
            entity_type="contacts",
            entity_id=test_contact.id,
            action="updated",
            changes=json.dumps([{"field": "email", "old_value": "old@test.com", "new_value": "new@test.com"}]),
            user_id=test_user.id,
            user_name=test_user.full_name,
            user_email=test_user.email,
        )
        db_session.add(entry)
        await db_session.commit()

        response = await client.get(
            f"/api/audit/contacts/{test_contact.id}",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert len(data["items"]) == 1

        item = data["items"][0]
        assert item["entity_type"] == "contacts"
        assert item["entity_id"] == test_contact.id
        assert item["action"] == "updated"
        assert item["user_name"] == test_user.full_name
        assert len(item["changes"]) == 1
        assert item["changes"][0]["field"] == "email"

    @pytest.mark.asyncio
    async def test_get_audit_log_pagination(
        self, client, auth_headers, db_session, test_user, test_contact
    ):
        """Should paginate audit log entries."""
        from src.audit.models import AuditLog

        for i in range(15):
            entry = AuditLog(
                entity_type="contacts",
                entity_id=test_contact.id,
                action="updated",
                user_id=test_user.id,
                user_name=test_user.full_name,
            )
            db_session.add(entry)
        await db_session.commit()

        # Page 1 (default page_size=10)
        response = await client.get(
            f"/api/audit/contacts/{test_contact.id}?page=1&page_size=10",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 10
        assert data["total"] == 15
        assert data["pages"] == 2

        # Page 2
        response = await client.get(
            f"/api/audit/contacts/{test_contact.id}?page=2&page_size=10",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 5

    @pytest.mark.asyncio
    async def test_get_audit_log_with_changes_detail(
        self, client, auth_headers, db_session, test_user, test_contact
    ):
        """Should return field-level change details."""
        from src.audit.models import AuditLog

        changes = [
            {"field": "email", "old_value": "old@test.com", "new_value": "new@test.com"},
            {"field": "phone", "old_value": "+1-555-0100", "new_value": "+1-555-0200"},
        ]
        entry = AuditLog(
            entity_type="contacts",
            entity_id=test_contact.id,
            action="updated",
            changes=json.dumps(changes),
            user_id=test_user.id,
        )
        db_session.add(entry)
        await db_session.commit()

        response = await client.get(
            f"/api/audit/contacts/{test_contact.id}",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        item = data["items"][0]
        assert len(item["changes"]) == 2
        assert item["changes"][0]["field"] == "email"
        assert item["changes"][1]["field"] == "phone"

    @pytest.mark.asyncio
    async def test_get_audit_log_requires_auth(self, client):
        """Should require authentication."""
        response = await client.get("/api/audit/contacts/1")
        assert response.status_code == 401
