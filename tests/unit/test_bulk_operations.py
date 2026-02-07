"""
Unit tests for bulk operations endpoints.

Tests for mass update and mass assign operations on CRM entities.
"""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from src.auth.models import User
from src.leads.models import Lead, LeadSource
from src.contacts.models import Contact
from src.companies.models import Company


@pytest.fixture
async def test_leads_batch(db_session: AsyncSession, test_user: User, test_lead_source: LeadSource):
    """Create a batch of test leads."""
    leads = []
    for i in range(5):
        lead = Lead(
            first_name=f"Lead{i}",
            last_name=f"Test{i}",
            email=f"lead{i}@example.com",
            status="new",
            score=10 + i * 10,
            source_id=test_lead_source.id,
            owner_id=test_user.id,
            created_by_id=test_user.id,
        )
        db_session.add(lead)
        leads.append(lead)
    await db_session.commit()
    for lead in leads:
        await db_session.refresh(lead)
    return leads


@pytest.fixture
async def second_user(db_session: AsyncSession) -> User:
    """Create a second user for assignment tests."""
    from src.auth.security import get_password_hash
    user = User(
        email="seconduser@example.com",
        hashed_password=get_password_hash("password123"),
        full_name="Second User",
        is_active=True,
        is_superuser=False,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


class TestBulkUpdate:
    """Tests for bulk update endpoint."""

    @pytest.mark.asyncio
    async def test_bulk_update_leads_status(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_leads_batch: list,
    ):
        """Test mass updating lead status."""
        lead_ids = [l.id for l in test_leads_batch[:3]]

        response = await client.post(
            "/api/import-export/bulk/update",
            headers=auth_headers,
            json={
                "entity_type": "leads",
                "entity_ids": lead_ids,
                "updates": {"status": "qualified"},
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["updated"] == 3
        assert data["entity_type"] == "leads"

        # Verify in database
        for lead_id in lead_ids:
            result = await db_session.execute(select(Lead).where(Lead.id == lead_id))
            lead = result.scalar_one()
            assert lead.status == "qualified"

    @pytest.mark.asyncio
    async def test_bulk_update_leads_score(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_leads_batch: list,
    ):
        """Test mass updating lead score."""
        lead_ids = [l.id for l in test_leads_batch[:2]]

        response = await client.post(
            "/api/import-export/bulk/update",
            headers=auth_headers,
            json={
                "entity_type": "leads",
                "entity_ids": lead_ids,
                "updates": {"score": 100},
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["updated"] == 2

    @pytest.mark.asyncio
    async def test_bulk_update_invalid_entity_type(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
    ):
        """Test bulk update with invalid entity type returns 400."""
        response = await client.post(
            "/api/import-export/bulk/update",
            headers=auth_headers,
            json={
                "entity_type": "nonexistent",
                "entity_ids": [1, 2],
                "updates": {"status": "test"},
            },
        )

        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_bulk_update_no_valid_fields(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
    ):
        """Test bulk update with disallowed fields returns 400."""
        response = await client.post(
            "/api/import-export/bulk/update",
            headers=auth_headers,
            json={
                "entity_type": "leads",
                "entity_ids": [1],
                "updates": {"email": "hacked@example.com"},
            },
        )

        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_bulk_update_empty_ids(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
    ):
        """Test bulk update with empty entity IDs returns 400."""
        response = await client.post(
            "/api/import-export/bulk/update",
            headers=auth_headers,
            json={
                "entity_type": "leads",
                "entity_ids": [],
                "updates": {"status": "qualified"},
            },
        )

        assert response.status_code == 400


class TestBulkAssign:
    """Tests for bulk assign endpoint."""

    @pytest.mark.asyncio
    async def test_bulk_assign_leads(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_leads_batch: list,
        second_user: User,
    ):
        """Test mass assigning leads to a different owner."""
        lead_ids = [l.id for l in test_leads_batch]

        response = await client.post(
            "/api/import-export/bulk/assign",
            headers=auth_headers,
            json={
                "entity_type": "leads",
                "entity_ids": lead_ids,
                "owner_id": second_user.id,
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["updated"] == 5
        assert data["owner_id"] == second_user.id

        # Verify in database
        for lead_id in lead_ids:
            result = await db_session.execute(select(Lead).where(Lead.id == lead_id))
            lead = result.scalar_one()
            assert lead.owner_id == second_user.id

    @pytest.mark.asyncio
    async def test_bulk_assign_invalid_entity_type(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
    ):
        """Test bulk assign with invalid entity type."""
        response = await client.post(
            "/api/import-export/bulk/assign",
            headers=auth_headers,
            json={
                "entity_type": "invalid",
                "entity_ids": [1],
                "owner_id": 1,
            },
        )

        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_bulk_assign_empty_ids(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
    ):
        """Test bulk assign with empty entity IDs."""
        response = await client.post(
            "/api/import-export/bulk/assign",
            headers=auth_headers,
            json={
                "entity_type": "leads",
                "entity_ids": [],
                "owner_id": 1,
            },
        )

        assert response.status_code == 400


class TestBulkOperationsUnauthorized:
    """Tests for unauthorized access to bulk operation endpoints."""

    @pytest.mark.asyncio
    async def test_bulk_update_unauthorized(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        response = await client.post(
            "/api/import-export/bulk/update",
            json={
                "entity_type": "leads",
                "entity_ids": [1],
                "updates": {"status": "qualified"},
            },
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_bulk_assign_unauthorized(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        response = await client.post(
            "/api/import-export/bulk/assign",
            json={
                "entity_type": "leads",
                "entity_ids": [1],
                "owner_id": 1,
            },
        )
        assert response.status_code == 401
