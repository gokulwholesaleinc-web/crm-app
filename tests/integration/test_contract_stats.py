"""Tests for the GET /api/contracts/stats aggregate endpoint."""

import pytest
from httpx import AsyncClient
from datetime import date, timedelta
from sqlalchemy.ext.asyncio import AsyncSession

from src.contracts.models import Contract
from src.auth.models import User


@pytest.mark.asyncio
class TestContractStats:
    """Contract stats endpoint returns correct aggregates for seeded data."""

    async def _seed_contracts(self, db_session: AsyncSession, user: User) -> None:
        today = date.today()
        in_15_days = today + timedelta(days=15)
        in_60_days = today + timedelta(days=60)

        contracts = [
            # Active contract with value + ending within 30d
            Contract(
                title="Active Soon",
                status="active",
                value=1000.0,
                currency="USD",
                owner_id=user.id,
                end_date=in_15_days,
            ),
            # Active contract with value + ending outside 30d
            Contract(
                title="Active Later",
                status="active",
                value=2500.0,
                currency="USD",
                owner_id=user.id,
                end_date=in_60_days,
            ),
            # Draft — not counted in active value
            Contract(
                title="Draft One",
                status="draft",
                value=500.0,
                currency="USD",
                owner_id=user.id,
            ),
            # Expired
            Contract(
                title="Expired One",
                status="expired",
                value=300.0,
                currency="USD",
                owner_id=user.id,
            ),
        ]
        for c in contracts:
            db_session.add(c)
        await db_session.commit()

    async def test_stats_total_active_value(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
        auth_headers: dict,
    ) -> None:
        """Should return sum of value only for active contracts."""
        await self._seed_contracts(db_session, test_user)
        response = await client.get("/api/contracts/stats", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        # Active contracts: 1000 + 2500 = 3500
        assert data["total_active_value"] == pytest.approx(3500.0)

    async def test_stats_expiring_this_month(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
        auth_headers: dict,
    ) -> None:
        """Should count only active contracts ending within 30 days."""
        await self._seed_contracts(db_session, test_user)
        response = await client.get("/api/contracts/stats", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        # Only "Active Soon" (in_15_days) qualifies
        assert data["expiring_this_month"] == 1

    async def test_stats_status_breakdown(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
        auth_headers: dict,
    ) -> None:
        """Should count contracts grouped by status correctly."""
        await self._seed_contracts(db_session, test_user)
        response = await client.get("/api/contracts/stats", headers=auth_headers)
        assert response.status_code == 200
        bd = response.json()["status_breakdown"]
        assert bd["active"] == 2
        assert bd["draft"] == 1
        assert bd["expired"] == 1
        assert bd["sent"] == 0
        assert bd["signed"] == 0
        assert bd["terminated"] == 0

    async def test_stats_requires_auth(
        self,
        client: AsyncClient,
    ) -> None:
        """Should return 401 for unauthenticated requests."""
        response = await client.get("/api/contracts/stats")
        assert response.status_code == 401
