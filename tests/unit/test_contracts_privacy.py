"""
Privacy / data-scoping tests for the contracts endpoints.

Verifies that:
  - admin (superuser) sees all contracts regardless of owner
  - sales_rep sees only their own contracts by default
  - sales_rep sees a contract that has been shared with them via EntityShare
  - sales_rep gets 403 on a contract they don't own and that hasn't been shared
  - sales_rep gets 200 on a contract shared with them (detail endpoint)
  - POST /api/sharing with entity_type=contracts succeeds

All tests use the real SQLite in-memory DB wired through the test client —
no mocks.
"""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.models import User
from src.contracts.models import Contract
from src.core.models import EntityShare


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _make_contract(
    db: AsyncSession,
    owner: User,
    title: str = "Test Contract",
) -> Contract:
    contract = Contract(
        title=title,
        status="draft",
        value=1000.0,
        currency="USD",
        owner_id=owner.id,
        created_by_id=owner.id,
    )
    db.add(contract)
    await db.commit()
    await db.refresh(contract)
    return contract


async def _share_contract(
    db: AsyncSession,
    contract: Contract,
    shared_with: User,
    shared_by: User,
    permission: str = "view",
) -> EntityShare:
    share = EntityShare(
        entity_type="contracts",
        entity_id=contract.id,
        shared_with_user_id=shared_with.id,
        shared_by_user_id=shared_by.id,
        permission_level=permission,
    )
    db.add(share)
    await db.commit()
    await db.refresh(share)
    return share


# ---------------------------------------------------------------------------
# Admin visibility
# ---------------------------------------------------------------------------

class TestAdminVisibility:
    """Admin (superuser) can see all contracts."""

    @pytest.mark.asyncio
    async def test_admin_sees_all_contracts(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_admin_user: User,
        admin_auth_headers: dict,
        _sales_rep_user: User,
    ):
        """Admin sees contracts owned by other users."""
        rep_contract = await _make_contract(db_session, _sales_rep_user, "Rep Contract")
        admin_contract = await _make_contract(db_session, test_admin_user, "Admin Contract")

        response = await client.get("/api/contracts", headers=admin_auth_headers)

        assert response.status_code == 200
        data = response.json()
        ids = [c["id"] for c in data["items"]]
        assert rep_contract.id in ids
        assert admin_contract.id in ids

    @pytest.mark.asyncio
    async def test_admin_can_fetch_any_contract_detail(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_admin_user: User,
        admin_auth_headers: dict,
        _sales_rep_user: User,
    ):
        """Admin can GET a contract they do not own."""
        rep_contract = await _make_contract(db_session, _sales_rep_user, "Rep Only Contract")

        response = await client.get(
            f"/api/contracts/{rep_contract.id}",
            headers=admin_auth_headers,
        )

        assert response.status_code == 200
        assert response.json()["id"] == rep_contract.id


# ---------------------------------------------------------------------------
# Sales-rep scoping
# ---------------------------------------------------------------------------

class TestSalesRepScoping:
    """Sales rep sees only own contracts unless shared."""

    @pytest.mark.asyncio
    async def test_sales_rep_sees_only_own_contracts_in_list(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_admin_user: User,
        _sales_rep_user: User,
        sales_rep_auth_headers: dict,
    ):
        """Sales rep list only includes contracts they own."""
        own_contract = await _make_contract(db_session, _sales_rep_user, "Own Contract")
        other_contract = await _make_contract(db_session, test_admin_user, "Admin Contract")

        response = await client.get("/api/contracts", headers=sales_rep_auth_headers)

        assert response.status_code == 200
        data = response.json()
        ids = [c["id"] for c in data["items"]]
        assert own_contract.id in ids
        assert other_contract.id not in ids

    @pytest.mark.asyncio
    async def test_sales_rep_sees_shared_contract_in_list(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_admin_user: User,
        _sales_rep_user: User,
        sales_rep_auth_headers: dict,
    ):
        """Sales rep list includes contracts shared with them."""
        shared_contract = await _make_contract(db_session, test_admin_user, "Shared With Rep")
        await _share_contract(
            db_session, shared_contract,
            shared_with=_sales_rep_user,
            shared_by=test_admin_user,
        )

        response = await client.get("/api/contracts", headers=sales_rep_auth_headers)

        assert response.status_code == 200
        data = response.json()
        ids = [c["id"] for c in data["items"]]
        assert shared_contract.id in ids

    @pytest.mark.asyncio
    async def test_sales_rep_gets_403_on_unshared_contract_detail(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_admin_user: User,
        _sales_rep_user: User,
        sales_rep_auth_headers: dict,
    ):
        """Sales rep cannot fetch detail of a contract they don't own and isn't shared."""
        admin_contract = await _make_contract(db_session, test_admin_user, "Admin Only")

        response = await client.get(
            f"/api/contracts/{admin_contract.id}",
            headers=sales_rep_auth_headers,
        )

        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_sales_rep_gets_200_on_shared_contract_detail(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_admin_user: User,
        _sales_rep_user: User,
        sales_rep_auth_headers: dict,
    ):
        """Sales rep can fetch detail of a contract shared with them."""
        shared_contract = await _make_contract(db_session, test_admin_user, "Shared Detail")
        await _share_contract(
            db_session, shared_contract,
            shared_with=_sales_rep_user,
            shared_by=test_admin_user,
        )

        response = await client.get(
            f"/api/contracts/{shared_contract.id}",
            headers=sales_rep_auth_headers,
        )

        assert response.status_code == 200
        assert response.json()["id"] == shared_contract.id


# ---------------------------------------------------------------------------
# Sharing endpoint
# ---------------------------------------------------------------------------

class TestSharingEndpoint:
    """POST /api/sharing with entity_type=contracts."""

    @pytest.mark.asyncio
    async def test_share_contract_via_sharing_endpoint(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_admin_user: User,
        admin_auth_headers: dict,
        _sales_rep_user: User,
    ):
        """Sharing a contract via the /api/sharing endpoint succeeds."""
        contract = await _make_contract(db_session, test_admin_user, "To Be Shared")

        response = await client.post(
            "/api/sharing",
            json={
                "entity_type": "contracts",
                "entity_id": contract.id,
                "shared_with_user_id": _sales_rep_user.id,
                "permission_level": "view",
            },
            headers=admin_auth_headers,
        )

        assert response.status_code == 201
        data = response.json()
        assert data["entity_type"] == "contracts"
        assert data["entity_id"] == contract.id
        assert data["shared_with_user_id"] == _sales_rep_user.id
