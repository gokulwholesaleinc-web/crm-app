"""E-sign workflow tests for contracts.

All tests use the real SQLite in-memory DB (via conftest fixtures).
No mocks — per CLAUDE.md.
"""

from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.models import User
from src.companies.models import Company
from src.contacts.models import Contact
from src.contracts.models import Contract
from src.contracts.service import ContractService
from src.email.models import EmailQueue


# ---------- helpers ----------


async def _make_contract(
    db: AsyncSession,
    owner: User,
    contact: Contact | None = None,
    company: Company | None = None,
    status: str = "draft",
) -> Contract:
    c = Contract(
        title="Test Services Contract",
        scope="Provide consulting services.",
        value=5000.0,
        currency="USD",
        status=status,
        owner_id=owner.id,
        contact_id=contact.id if contact else None,
        company_id=company.id if company else None,
    )
    db.add(c)
    await db.commit()
    await db.refresh(c)
    return c


async def _make_contact_with_email(db: AsyncSession, owner: User, email: str) -> Contact:
    contact = Contact(
        first_name="Jane",
        last_name="Signer",
        email=email,
        status="active",
        owner_id=owner.id,
        created_by_id=owner.id,
    )
    db.add(contact)
    await db.commit()
    await db.refresh(contact)
    return contact


# ---------- service-level tests ----------


class TestSendForSignature:
    """Send happy path."""

    async def test_send_sets_token_and_status(
        self, db_session: AsyncSession, test_user: User, test_contact: Contact
    ):
        contract = await _make_contract(db_session, test_user, contact=test_contact)
        svc = ContractService(db_session)

        result = await svc.send_for_signature(contract, user_id=test_user.id)

        assert result.status == "sent"
        assert result.sign_token is not None and len(result.sign_token) >= 16
        assert result.sent_at is not None
        expires = result.sign_token_expires_at
        assert expires is not None
        # Should be ~7 days from now (within a 10s window).
        # Coerce naive (SQLite) to UTC for comparison.
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=UTC)
        delta = expires - datetime.now(UTC)
        assert timedelta(days=6, hours=23) < delta < timedelta(days=7, seconds=10)

    async def test_send_queues_email(
        self, db_session: AsyncSession, test_user: User, test_contact: Contact
    ):
        contract = await _make_contract(db_session, test_user, contact=test_contact)
        svc = ContractService(db_session)
        await svc.send_for_signature(contract, user_id=test_user.id)

        from sqlalchemy import select
        result = await db_session.execute(
            select(EmailQueue).where(EmailQueue.entity_type == "contracts").where(EmailQueue.entity_id == contract.id)
        )
        rows = list(result.scalars().all())
        assert len(rows) == 1
        assert test_contact.email in rows[0].to_email

    async def test_send_rejects_signed_contract(
        self, db_session: AsyncSession, test_user: User, test_contact: Contact
    ):
        contract = await _make_contract(db_session, test_user, contact=test_contact, status="signed")
        svc = ContractService(db_session)

        with pytest.raises(ValueError, match="signed"):
            await svc.send_for_signature(contract, user_id=test_user.id)

    async def test_send_raises_without_email(
        self, db_session: AsyncSession, test_user: User
    ):
        contract = await _make_contract(db_session, test_user)  # no contact
        svc = ContractService(db_session)

        with pytest.raises(ValueError, match="No recipient email"):
            await svc.send_for_signature(contract, user_id=test_user.id)

    async def test_send_with_explicit_to_email(
        self, db_session: AsyncSession, test_user: User
    ):
        contract = await _make_contract(db_session, test_user)
        svc = ContractService(db_session)

        result = await svc.send_for_signature(
            contract, user_id=test_user.id, to_email="external@client.com"
        )
        assert result.status == "sent"

    async def test_send_remints_token_on_resend(
        self, db_session: AsyncSession, test_user: User, test_contact: Contact
    ):
        contract = await _make_contract(db_session, test_user, contact=test_contact)
        svc = ContractService(db_session)

        await svc.send_for_signature(contract, user_id=test_user.id)
        first_token = contract.sign_token

        await svc.send_for_signature(contract, user_id=test_user.id)
        assert contract.sign_token != first_token


class TestGetPublicView:
    """Public view projection."""

    async def test_public_view_fields(
        self, db_session: AsyncSession, test_user: User, test_contact: Contact
    ):
        contract = await _make_contract(db_session, test_user, contact=test_contact)
        svc = ContractService(db_session)
        await svc.send_for_signature(contract, user_id=test_user.id)

        view = await svc.get_public_view(contract)

        assert view["id"] == contract.id
        assert view["title"] == contract.title
        assert view["signer_email"] == test_contact.email.lower()
        assert view["expires_at"] is not None
        assert isinstance(view["branding"], dict)

    async def test_public_view_does_not_mutate(
        self, db_session: AsyncSession, test_user: User, test_contact: Contact
    ):
        contract = await _make_contract(db_session, test_user, contact=test_contact)
        svc = ContractService(db_session)
        await svc.send_for_signature(contract, user_id=test_user.id)
        original_status = contract.status

        await svc.get_public_view(contract)
        assert contract.status == original_status


class TestSignContract:
    """Sign happy path and rejection cases."""

    DUMMY_SIGNATURE = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="

    async def test_sign_happy_path(
        self, db_session: AsyncSession, test_user: User, test_contact: Contact
    ):
        contract = await _make_contract(db_session, test_user, contact=test_contact)
        svc = ContractService(db_session)
        await svc.send_for_signature(contract, user_id=test_user.id)

        result = await svc.sign_contract(
            contract,
            signer_name="Jane Signer",
            signer_email=test_contact.email,
            signature_data_url=self.DUMMY_SIGNATURE,
            signer_ip="127.0.0.1",
            signer_ua="TestBrowser/1.0",
        )

        assert result.status == "signed"
        assert result.signed_at is not None
        assert result.signed_by_name == "Jane Signer"
        assert result.sign_token is None
        assert result.sign_token_expires_at is None

    async def test_sign_rejects_expired_token(
        self, db_session: AsyncSession, test_user: User, test_contact: Contact
    ):
        contract = await _make_contract(db_session, test_user, contact=test_contact)
        svc = ContractService(db_session)
        await svc.send_for_signature(contract, user_id=test_user.id)

        # Manually expire the token
        contract.sign_token_expires_at = datetime.now(UTC) - timedelta(hours=1)
        await db_session.commit()

        with pytest.raises(ValueError, match="expired"):
            await svc.sign_contract(
                contract,
                signer_name="Jane",
                signer_email=test_contact.email,
                signature_data_url=self.DUMMY_SIGNATURE,
            )

    async def test_sign_rejects_wrong_status(
        self, db_session: AsyncSession, test_user: User, test_contact: Contact
    ):
        contract = await _make_contract(db_session, test_user, contact=test_contact, status="draft")
        svc = ContractService(db_session)

        with pytest.raises(ValueError, match="draft"):
            await svc.sign_contract(
                contract,
                signer_name="Jane",
                signer_email=test_contact.email,
                signature_data_url=self.DUMMY_SIGNATURE,
            )

    async def test_sign_rejects_mismatched_email(
        self, db_session: AsyncSession, test_user: User, test_contact: Contact
    ):
        contract = await _make_contract(db_session, test_user, contact=test_contact)
        svc = ContractService(db_session)
        await svc.send_for_signature(contract, user_id=test_user.id)

        with pytest.raises(ValueError, match="email"):
            await svc.sign_contract(
                contract,
                signer_name="Evil",
                signer_email="wrong@attacker.com",
                signature_data_url=self.DUMMY_SIGNATURE,
            )

    async def test_sign_no_contact_allows_any_email(
        self, db_session: AsyncSession, test_user: User
    ):
        """When no contact is linked, any email is accepted."""
        contract = await _make_contract(db_session, test_user)
        svc = ContractService(db_session)
        await svc.send_for_signature(contract, user_id=test_user.id, to_email="any@example.com")

        result = await svc.sign_contract(
            contract,
            signer_name="Anyone",
            signer_email="any@example.com",
            signature_data_url=self.DUMMY_SIGNATURE,
        )
        assert result.status == "signed"

    async def test_concurrent_sign_second_raises(
        self, db_session: AsyncSession, test_user: User, test_contact: Contact
    ):
        """Simulate second signer attempt after first flipped status.

        The test directly calls the _atomic_ UPDATE path by pre-flipping the DB
        row to 'signed' via raw SQL (mimicking what the first signer's commit
        does), then verifies that sign_contract raises when rowcount==0.
        """
        from sqlalchemy import text

        contract = await _make_contract(db_session, test_user, contact=test_contact)
        svc = ContractService(db_session)
        await svc.send_for_signature(contract, user_id=test_user.id)

        # Pre-flip the DB row to 'signed' to simulate a concurrent first signer
        # that already committed (the in-memory object still thinks it's 'sent').
        await db_session.execute(
            text("UPDATE contracts SET status='signed' WHERE id=:id"),
            {"id": contract.id},
        )
        # Expire the in-memory object so we don't autoflush the old status back.
        await db_session.commit()

        # Reload from DB — status is now 'signed'
        await db_session.refresh(contract)

        # The token is cleared; restore it so the expiry check passes.
        # (In prod the concurrent request would have the token from when it
        # loaded the contract — before the first signer's commit cleared it.)
        contract.sign_token = "fake-token-for-test"
        contract.sign_token_expires_at = datetime.now(UTC) + timedelta(hours=1)

        with pytest.raises(ValueError, match="signed"):
            await svc.sign_contract(
                contract,
                signer_name="Jane",
                signer_email=test_contact.email,
                signature_data_url=self.DUMMY_SIGNATURE,
            )


# ---------- router-level tests ----------


class TestContractEsignRoutes:
    """HTTP-level tests for the three e-sign endpoints."""

    DUMMY_SIGNATURE = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="

    async def _create_and_send(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
        auth_headers: dict,
        test_contact: Contact,
    ) -> tuple[int, str]:
        """Helper: create a contract and send for signature; return (id, token)."""
        create_resp = await client.post(
            "/api/contracts",
            json={
                "title": "Router Test Contract",
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
        data = send_resp.json()
        token = data["sign_url"].split("/")[-1]
        return contract_id, token

    async def test_send_endpoint_returns_sign_url(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
        auth_headers: dict,
        test_contact: Contact,
    ):
        _, token = await self._create_and_send(client, db_session, test_user, auth_headers, test_contact)
        assert len(token) >= 16

    async def test_public_get_returns_200(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
        auth_headers: dict,
        test_contact: Contact,
    ):
        _, token = await self._create_and_send(client, db_session, test_user, auth_headers, test_contact)
        resp = await client.get(f"/api/contracts/public/{token}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["title"] == "Router Test Contract"
        assert data["signer_email"] == test_contact.email.lower()
        assert "branding" in data

    async def test_public_get_404_on_bad_token(self, client: AsyncClient):
        resp = await client.get("/api/contracts/public/no-such-token-at-all-xxxx")
        assert resp.status_code == 404

    async def test_sign_endpoint_returns_200(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
        auth_headers: dict,
        test_contact: Contact,
    ):
        _, token = await self._create_and_send(client, db_session, test_user, auth_headers, test_contact)
        resp = await client.post(
            f"/api/contracts/public/{token}/sign",
            json={
                "signer_name": "Jane Signer",
                "signer_email": test_contact.email,
                "signature_data_url": self.DUMMY_SIGNATURE,
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "signed"
        assert data["signed_by_name"] == "Jane Signer"

    async def test_sign_400_on_expired_token(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
        auth_headers: dict,
        test_contact: Contact,
    ):
        contract_id, token = await self._create_and_send(
            client, db_session, test_user, auth_headers, test_contact
        )
        # Expire the token via DB
        from sqlalchemy import select, update as sa_update
        from src.contracts.models import Contract as ContractModel
        await db_session.execute(
            sa_update(ContractModel)
            .where(ContractModel.id == contract_id)
            .values(sign_token_expires_at=datetime.now(UTC) - timedelta(hours=1))
        )
        await db_session.commit()

        resp = await client.post(
            f"/api/contracts/public/{token}/sign",
            json={
                "signer_name": "Jane",
                "signer_email": test_contact.email,
                "signature_data_url": self.DUMMY_SIGNATURE,
            },
        )
        assert resp.status_code == 400
        assert "expired" in resp.json()["detail"].lower()
