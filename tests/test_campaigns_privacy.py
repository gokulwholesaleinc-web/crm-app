"""Integration tests for campaign privacy parity.

Verifies that:
- admin sees all campaigns in the list
- sales_rep sees only their own campaigns in the list
- sales_rep sees a campaign shared with them via EntityShare in the list
- sales_rep gets 403 on detail of a non-owned, non-shared campaign
- sales_rep gets 200 on detail of a shared campaign
- POST /api/sharing with entity_type='campaigns' succeeds

No mocks — all tests run against the in-memory SQLite test database using
the real FastAPI app and the fixtures from conftest.py.
"""

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from src.auth.models import User
from src.auth.security import create_access_token
from src.campaigns.models import Campaign
from src.core.models import EntityShare

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _auth(user: User) -> dict:
    token = create_access_token(data={"sub": str(user.id)})
    return {"Authorization": f"Bearer {token}"}


async def _create_campaign(
    db: AsyncSession,
    owner: User,
    name: str,
) -> Campaign:
    campaign = Campaign(
        name=name,
        campaign_type="email",
        status="planned",
        owner_id=owner.id,
        created_by_id=owner.id,
    )
    db.add(campaign)
    await db.commit()
    await db.refresh(campaign)
    return campaign


async def _share_campaign(
    db: AsyncSession,
    campaign: Campaign,
    shared_with: User,
    shared_by: User,
    permission_level: str = "view",
) -> EntityShare:
    share = EntityShare(
        entity_type="campaigns",
        entity_id=campaign.id,
        shared_with_user_id=shared_with.id,
        shared_by_user_id=shared_by.id,
        permission_level=permission_level,
    )
    db.add(share)
    await db.commit()
    await db.refresh(share)
    return share


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestCampaignPrivacy:
    async def test_admin_sees_all_campaigns_in_list(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_admin_user: User,
        _sales_rep_user: User,
        seed_roles,
    ):
        """Admin user sees campaigns owned by any user in the list endpoint."""
        c1 = await _create_campaign(db_session, test_admin_user, "Admin Campaign")
        c2 = await _create_campaign(db_session, _sales_rep_user, "Rep Campaign")

        response = await client.get("/api/campaigns", headers=_auth(test_admin_user))
        assert response.status_code == 200
        data = response.json()
        ids = {item["id"] for item in data["items"]}
        assert c1.id in ids
        assert c2.id in ids

    async def test_sales_rep_sees_only_own_campaigns_in_list(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_admin_user: User,
        _sales_rep_user: User,
        seed_roles,
    ):
        """Sales rep only sees their own campaigns — not other owners' campaigns."""
        own = await _create_campaign(db_session, _sales_rep_user, "My Campaign")
        other = await _create_campaign(db_session, test_admin_user, "Not My Campaign")

        response = await client.get("/api/campaigns", headers=_auth(_sales_rep_user))
        assert response.status_code == 200
        data = response.json()
        ids = {item["id"] for item in data["items"]}
        assert own.id in ids
        assert other.id not in ids

    async def test_sales_rep_sees_shared_campaign_in_list(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_admin_user: User,
        _sales_rep_user: User,
        seed_roles,
    ):
        """Sales rep sees a campaign owned by someone else when it has been shared with them."""
        shared = await _create_campaign(db_session, test_admin_user, "Shared Campaign")
        await _share_campaign(db_session, shared, _sales_rep_user, test_admin_user)

        response = await client.get("/api/campaigns", headers=_auth(_sales_rep_user))
        assert response.status_code == 200
        data = response.json()
        ids = {item["id"] for item in data["items"]}
        assert shared.id in ids

    async def test_sales_rep_gets_403_on_unshared_campaign_detail(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_admin_user: User,
        _sales_rep_user: User,
        seed_roles,
    ):
        """Sales rep cannot access the detail of a campaign they neither own nor have a share for."""
        foreign = await _create_campaign(db_session, test_admin_user, "Admin Only Campaign")

        response = await client.get(
            f"/api/campaigns/{foreign.id}", headers=_auth(_sales_rep_user)
        )
        assert response.status_code == 403

    async def test_sales_rep_gets_200_on_shared_campaign_detail(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_admin_user: User,
        _sales_rep_user: User,
        seed_roles,
    ):
        """Sales rep can access the detail of a campaign that has been shared with them."""
        shared = await _create_campaign(db_session, test_admin_user, "Shared Detail Campaign")
        await _share_campaign(db_session, shared, _sales_rep_user, test_admin_user)

        response = await client.get(
            f"/api/campaigns/{shared.id}", headers=_auth(_sales_rep_user)
        )
        assert response.status_code == 200
        assert response.json()["id"] == shared.id

    async def test_post_sharing_with_campaigns_entity_type_succeeds(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_admin_user: User,
        _sales_rep_user: User,
        seed_roles,
    ):
        """POST /api/sharing with entity_type='campaigns' creates a share row and returns 201."""
        campaign = await _create_campaign(db_session, test_admin_user, "To Be Shared")

        payload = {
            "entity_type": "campaigns",
            "entity_id": campaign.id,
            "shared_with_user_id": _sales_rep_user.id,
            "permission_level": "view",
        }
        response = await client.post("/api/sharing", json=payload, headers=_auth(test_admin_user))
        assert response.status_code == 201
        body = response.json()
        assert body["entity_type"] == "campaigns"
        assert body["entity_id"] == campaign.id
        assert body["shared_with_user_id"] == _sales_rep_user.id
        assert body["permission_level"] == "view"
