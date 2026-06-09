"""Marketing admin connect-flow (E1) — auth gates, token-at-rest, A10, E7 purge.

SQLite app harness. Asserts the security contract: admin-only, dark behind the
flag, pasted tokens encrypted + never echoed, A10 normalization on write, and the
E7 disconnect (tokens nulled, facts purged, connection disabled, audit kept).
"""

from datetime import date
from decimal import Decimal

import pytest_asyncio
from cryptography.fernet import Fernet
from src.marketing.models import AdsDailyMetric, PlatformConnection


@pytest_asyncio.fixture(autouse=True)
async def _admin_env(monkeypatch):
    from src.config import settings
    from src.core.cache import app_cache

    await app_cache.clear()
    monkeypatch.setattr(settings, "MKTG_ENABLED", True)
    monkeypatch.setenv("MARKETING_TOKEN_KEY", Fernet.generate_key().decode())
    yield
    await app_cache.clear()


def _admin(superuser_token: str) -> dict:
    return {"Authorization": f"Bearer {superuser_token}"}


async def _create(client, headers, company_id, **over):
    body = {
        "platform": "google_ads",
        "external_account_id": "832-867-5647",
        "access_token": "paste-oauth-token",
        "currency": "USD",
        "manager_account_id": "832-867-5647",
        **over,
    }
    return await client.post(
        f"/api/marketing/admin/companies/{company_id}/connections", json=body, headers=headers
    )


class TestAuthGates:
    async def test_non_admin_forbidden(self, client, auth_headers, test_company):
        r = await _create(client, auth_headers, test_company.id)
        assert r.status_code == 403

    async def test_dark_when_flag_off(self, client, superuser_token, test_company, monkeypatch):
        from src.config import settings

        monkeypatch.setattr(settings, "MKTG_ENABLED", False)
        r = await _create(client, _admin(superuser_token), test_company.id)
        assert r.status_code == 404


class TestCreate:
    async def test_create_normalizes_and_encrypts_without_echoing_token(
        self, client, superuser_token, db_session, test_company
    ):
        r = await _create(client, _admin(superuser_token), test_company.id)
        assert r.status_code == 201
        body = r.json()
        # A10: dashes stripped to the 10-digit customer id.
        assert body["external_account_id"] == "8328675647"
        assert body["has_token"] is True
        assert body["status"] == "pending"
        # the token is NEVER echoed back, in any field
        assert "paste-oauth-token" not in r.text
        assert "access_token" not in body
        # stored ciphertext is real encryption, not the plaintext
        conn = (
            await db_session.execute(
                select_conn(test_company.id)
            )
        ).scalar_one()
        assert conn.access_token_ciphertext is not None
        assert b"paste-oauth-token" not in conn.access_token_ciphertext

    async def test_duplicate_identity_conflicts(self, client, superuser_token, test_company):
        h = _admin(superuser_token)
        assert (await _create(client, h, test_company.id)).status_code == 201
        # same account under a different spelling normalizes to the same id → 409
        r = await _create(client, h, test_company.id, external_account_id="8328675647")
        assert r.status_code == 409

    async def test_unknown_platform_rejected(self, client, superuser_token, test_company):
        r = await _create(client, _admin(superuser_token), test_company.id, platform="myspace")
        assert r.status_code == 422

    async def test_missing_company_404(self, client, superuser_token):
        r = await _create(client, _admin(superuser_token), 999999)
        assert r.status_code == 404


class TestListUpdateDisconnect:
    async def test_list_returns_connections_without_tokens(self, client, superuser_token, test_company):
        h = _admin(superuser_token)
        await _create(client, h, test_company.id)
        r = await client.get(
            f"/api/marketing/admin/companies/{test_company.id}/connections", headers=h
        )
        assert r.status_code == 200
        rows = r.json()
        assert len(rows) == 1
        assert "access_token" not in rows[0]
        assert rows[0]["has_token"] is True

    async def test_rotate_token_clears_reauth(self, client, superuser_token, db_session, test_company):
        h = _admin(superuser_token)
        cid = (await _create(client, h, test_company.id)).json()["id"]
        # force a needs_reauth, then rotate
        conn = await db_session.get(PlatformConnection, cid)
        conn.status = "needs_reauth"
        conn.failure_count = 4
        await db_session.commit()
        r = await client.patch(
            f"/api/marketing/admin/connections/{cid}",
            json={"access_token": "fresh-token"},
            headers=h,
        )
        assert r.status_code == 200
        assert r.json()["status"] == "pending"  # reauth cleared, retry armed

    async def test_disconnect_purges_facts_and_disables(
        self, client, superuser_token, db_session, test_company
    ):
        h = _admin(superuser_token)
        cid = (await _create(client, h, test_company.id)).json()["id"]
        # seed a fact row for this connection
        db_session.add(
            AdsDailyMetric(
                connection_id=cid, company_id=test_company.id, platform="google_ads",
                date=date(2026, 6, 1), entity_level="account", spend=Decimal("5"),
                impressions=10, clicks=1, conversions=Decimal("0"), conversion_value=Decimal("0"),
            )
        )
        await db_session.commit()

        r = await client.delete(f"/api/marketing/admin/connections/{cid}", headers=h)
        assert r.status_code == 204

        db_session.expire_all()
        conn = await db_session.get(PlatformConnection, cid)
        assert conn.status == "disabled"
        assert conn.is_enabled is False
        assert conn.access_token_ciphertext is None  # tokens hard-deleted (E7)
        remaining = (
            await db_session.execute(count_ads(cid))
        ).scalar_one()
        assert remaining == 0  # facts purged (E7)


# Small query helpers kept out of the test bodies for readability.
def select_conn(company_id):
    from sqlalchemy import select

    return select(PlatformConnection).where(PlatformConnection.company_id == company_id)


def count_ads(connection_id):
    from sqlalchemy import func, select

    return select(func.count()).select_from(AdsDailyMetric).where(
        AdsDailyMetric.connection_id == connection_id
    )
