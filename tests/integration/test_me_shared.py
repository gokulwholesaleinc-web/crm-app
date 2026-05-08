"""Tests for GET /api/me/shared — shared-with-me dashboard endpoint.

Tests cover:
- A record shared with the current user appears under the correct entity_type.
- Cap at 5 most-recent per entity_type (7 shares → 5 returned).
- owner_name is correctly hydrated from the User table.
- A user with no shares receives items_by_type={} and total=0.

Tests do NOT mock anything; they use the in-memory SQLite test DB.
"""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.models import User
from src.auth.security import create_access_token, get_password_hash
from src.core.models import EntityShare
from src.leads.models import Lead, LeadSource


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _make_user(db: AsyncSession, email: str, full_name: str) -> User:
    user = User(
        email=email,
        hashed_password=get_password_hash("pw123"),
        full_name=full_name,
        is_active=True,
        is_superuser=False,
    )
    db.add(user)
    await db.flush()
    return user


async def _make_lead_source(db: AsyncSession) -> LeadSource:
    src = LeadSource(name="Test Source", is_active=True)
    db.add(src)
    await db.flush()
    return src


async def _make_lead(db: AsyncSession, owner: User, source: LeadSource, first_name: str) -> Lead:
    lead = Lead(
        first_name=first_name,
        last_name="TestLast",
        email=f"{first_name.lower()}@example.com",
        status="new",
        source_id=source.id,
        owner_id=owner.id,
        created_by_id=owner.id,
    )
    db.add(lead)
    await db.flush()
    return lead


async def _share(
    db: AsyncSession,
    entity_type: str,
    entity_id: int,
    shared_with: User,
    shared_by: User,
    permission_level: str = "view",
) -> EntityShare:
    share = EntityShare(
        entity_type=entity_type,
        entity_id=entity_id,
        shared_with_user_id=shared_with.id,
        shared_by_user_id=shared_by.id,
        permission_level=permission_level,
    )
    db.add(share)
    await db.flush()
    return share


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestGetSharedWithMe:
    """Tests for GET /api/me/shared."""

    @pytest.mark.asyncio
    async def test_shared_lead_appears_in_response(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ):
        """A lead shared with the current user is returned under 'leads'."""
        owner = await _make_user(db_session, "owner@example.com", "Owner Person")
        viewer = await _make_user(db_session, "viewer@example.com", "Viewer Person")
        source = await _make_lead_source(db_session)
        lead = await _make_lead(db_session, owner, source, "Shared")
        await _share(db_session, "leads", lead.id, viewer, owner, "view")
        await db_session.commit()

        token = create_access_token(data={"sub": str(viewer.id)})
        response = await client.get(
            "/api/me/shared",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "leads" in data["items_by_type"]
        assert data["total"] >= 1
        item = data["items_by_type"]["leads"][0]
        assert item["entity_id"] == lead.id
        assert item["entity_type"] == "leads"
        assert item["permission_level"] == "view"

    @pytest.mark.asyncio
    async def test_cap_at_five_per_entity_type(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ):
        """7 shares of the same entity_type → only 5 returned."""
        owner = await _make_user(db_session, "cap_owner@example.com", "Cap Owner")
        viewer = await _make_user(db_session, "cap_viewer@example.com", "Cap Viewer")
        source = await _make_lead_source(db_session)

        for i in range(7):
            lead = await _make_lead(db_session, owner, source, f"Lead{i}")
            await _share(db_session, "leads", lead.id, viewer, owner)

        await db_session.commit()

        token = create_access_token(data={"sub": str(viewer.id)})
        response = await client.get(
            "/api/me/shared",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["items_by_type"]["leads"]) == 5
        assert data["total"] == 5

    @pytest.mark.asyncio
    async def test_owner_name_is_hydrated(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ):
        """owner_name in each item matches the full_name of the lead's owner."""
        owner = await _make_user(db_session, "hydrate_owner@example.com", "Hydrated Owner")
        viewer = await _make_user(db_session, "hydrate_viewer@example.com", "Hydrated Viewer")
        source = await _make_lead_source(db_session)
        lead = await _make_lead(db_session, owner, source, "HydrateTest")
        await _share(db_session, "leads", lead.id, viewer, owner)
        await db_session.commit()

        token = create_access_token(data={"sub": str(viewer.id)})
        response = await client.get(
            "/api/me/shared",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        data = response.json()
        item = data["items_by_type"]["leads"][0]
        assert item["owner_name"] == "Hydrated Owner"

    @pytest.mark.asyncio
    async def test_no_shares_returns_empty(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ):
        """A user who owns no shares gets items_by_type={} and total=0."""
        user = await _make_user(db_session, "empty_user@example.com", "Empty User")
        await db_session.commit()

        token = create_access_token(data={"sub": str(user.id)})
        response = await client.get(
            "/api/me/shared",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["items_by_type"] == {}
        assert data["total"] == 0
