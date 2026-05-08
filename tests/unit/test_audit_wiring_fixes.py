"""Regression tests for audit-wiring fixes.

Covers:

1. ``GET /api/dashboard/sales-kpis`` ``payments_collected_*`` must be scoped to
   ``current_user.id``. Prior bug: filter omitted ``Payment.owner_id``, exposing
   the whole tenant's totals to every user.
2. ``POST /api/sharing`` writes an ``AuditLog`` row keyed to the shared record.
3. ``DELETE /api/sharing/{id}`` writes an ``AuditLog`` row keyed to the record.
4. ``POST /api/contracts/public/{token}/sign`` emits exactly one
   ``contract_signed`` Notification row (router-level duplicate dispatch
   removed).

All tests use the real SQLite in-memory DB via existing conftest fixtures.
No mocks — per CLAUDE.md.
"""

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.audit.models import AuditLog
from src.auth.models import User
from src.auth.security import create_access_token, get_password_hash
from src.contacts.models import Contact
from src.dashboard.router import _dashboard_cache
from src.notifications.models import Notification
from src.payments.models import Payment


# ---------------------------------------------------------------------------
# Helpers / shared fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def other_user(db_session: AsyncSession) -> User:
    """A second user — used as the foreign Payment owner / share recipient."""
    user = User(
        email="other_audit_user@example.com",
        hashed_password=get_password_hash("password123"),
        full_name="Other User",
        is_active=True,
        is_superuser=False,
        role="sales_rep",
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


def _headers(user: User) -> dict:
    token = create_access_token(data={"sub": str(user.id)})
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# 1. Sales-KPIs payments scoping
# ---------------------------------------------------------------------------


class TestSalesKpisPaymentsScoping:
    """Regression for the data leak in ``/api/dashboard/sales-kpis``."""

    @pytest.mark.asyncio
    async def test_other_users_payments_are_excluded(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
        other_user: User,
        auth_headers: dict,
    ):
        # Clear the dashboard cache so we don't get a stale value from another test.
        _dashboard_cache.clear()

        mine = Payment(
            amount=111.00,
            currency="USD",
            status="succeeded",
            owner_id=test_user.id,
            created_by_id=test_user.id,
        )
        theirs = Payment(
            amount=999.00,
            currency="USD",
            status="succeeded",
            owner_id=other_user.id,
            created_by_id=other_user.id,
        )
        db_session.add_all([mine, theirs])
        await db_session.commit()

        resp = await client.get("/api/dashboard/sales-kpis", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        # Only the caller's payment should be counted; total must equal that
        # one row's amount, not the tenant aggregate.
        assert data["payments_collected_count"] == 1
        assert float(data["payments_collected_total"]) == pytest.approx(111.00)


# ---------------------------------------------------------------------------
# 2 + 3. Sharing audit log
# ---------------------------------------------------------------------------


class TestSharingAuditLog:
    """Share create + revoke must emit AuditLog rows on the shared record."""

    @pytest.mark.asyncio
    async def test_share_creates_audit_row(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
        other_user: User,
        test_contact: Contact,
        auth_headers: dict,
    ):
        resp = await client.post(
            "/api/sharing",
            json={
                "entity_type": "contacts",
                "entity_id": test_contact.id,
                "shared_with_user_id": other_user.id,
                "permission_level": "view",
            },
            headers=auth_headers,
        )
        assert resp.status_code == 201

        rows = (
            await db_session.execute(
                select(AuditLog).where(
                    AuditLog.entity_type == "contact",
                    AuditLog.entity_id == test_contact.id,
                    AuditLog.action == "share",
                )
            )
        ).scalars().all()
        assert len(rows) == 1
        assert rows[0].user_id == test_user.id
        assert rows[0].changes is not None
        assert rows[0].changes[0]["new"] == other_user.id
        assert rows[0].changes[0]["permission_level"] == "view"

    @pytest.mark.asyncio
    async def test_revoke_creates_audit_row(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
        other_user: User,
        test_contact: Contact,
        auth_headers: dict,
    ):
        share_resp = await client.post(
            "/api/sharing",
            json={
                "entity_type": "contacts",
                "entity_id": test_contact.id,
                "shared_with_user_id": other_user.id,
                "permission_level": "edit",
            },
            headers=auth_headers,
        )
        assert share_resp.status_code == 201
        share_id = share_resp.json()["id"]

        revoke_resp = await client.delete(
            f"/api/sharing/{share_id}", headers=auth_headers
        )
        assert revoke_resp.status_code == 204

        rows = (
            await db_session.execute(
                select(AuditLog).where(
                    AuditLog.entity_type == "contact",
                    AuditLog.entity_id == test_contact.id,
                    AuditLog.action == "unshare",
                )
            )
        ).scalars().all()
        assert len(rows) == 1
        assert rows[0].user_id == test_user.id
        assert rows[0].changes[0]["old"] == other_user.id
        assert rows[0].changes[0]["new"] is None
        assert rows[0].changes[0]["permission_level"] == "edit"


# ---------------------------------------------------------------------------
# 4. Contract sign no-double-fire
# ---------------------------------------------------------------------------


class TestContractSignNoDoubleFire:
    """``contract_signed`` Notification must be emitted exactly once per sign.

    Prior bug: the public-sign router created a raw notification AND
    ``ContractService.sign_contract`` called ``notify_on_contract_signed``,
    so the owner got two in-app rows per signature.
    """

    DUMMY_SIGNATURE = (
        "data:image/png;base64,"
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
    )

    @pytest.mark.asyncio
    async def test_signing_creates_one_notification(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
        test_contact: Contact,
        auth_headers: dict,
    ):
        create_resp = await client.post(
            "/api/contracts",
            json={
                "title": "Audit-fix Contract",
                "contact_id": test_contact.id,
                "owner_id": test_user.id,
            },
            headers=auth_headers,
        )
        assert create_resp.status_code == 201
        contract_id = create_resp.json()["id"]

        send_resp = await client.post(
            f"/api/contracts/{contract_id}/send",
            json={},
            headers=auth_headers,
        )
        assert send_resp.status_code == 200
        token = send_resp.json()["sign_url"].split("/")[-1]

        sign_resp = await client.post(
            f"/api/contracts/public/{token}/sign",
            json={
                "signer_name": "Jane Signer",
                "signer_email": test_contact.email,
                "signature_data_url": self.DUMMY_SIGNATURE,
            },
        )
        assert sign_resp.status_code == 200

        notifs = (
            await db_session.execute(
                select(Notification).where(
                    Notification.user_id == test_user.id,
                    Notification.type == "contract_signed",
                    Notification.entity_type == "contracts",
                    Notification.entity_id == contract_id,
                )
            )
        ).scalars().all()
        assert len(notifs) == 1, (
            f"expected exactly 1 contract_signed notification, got {len(notifs)}"
        )
