"""
Unit tests for the POST /api/integrations/gmail/relink admin endpoint.

Uses SQLite in-memory DB + httpx.AsyncClient test client (same pattern as
test_gmail_sync.py). find_contact_id_by_any_email is imported from
src.contacts.alias_match (Worker B's module); the import is guarded so
scaffolding compiles even before B pushes.
"""

import os
import sys

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "backend"))

from src.database import Base, get_db
from src.auth.models import User
from src.auth.security import get_password_hash
from src.contacts.models import Contact
from src.auth.dependencies import get_current_active_user, get_current_superuser
from src.email.models import EmailQueue
from src.integrations.gmail.router import router as gmail_router

TEST_DB_URL = "sqlite+aiosqlite:///:memory:"

# ---------------------------------------------------------------------------
# DB fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def engine():
    eng = create_async_engine(
        TEST_DB_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        echo=False,
    )
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await eng.dispose()


@pytest_asyncio.fixture
async def db(engine) -> AsyncSession:
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with maker() as session:
        yield session
        await session.rollback()


# ---------------------------------------------------------------------------
# User fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def admin_user(db: AsyncSession) -> User:
    user = User(
        email="admin@example.com",
        hashed_password=get_password_hash("pw"),
        full_name="Admin",
        is_active=True,
        is_superuser=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@pytest_asyncio.fixture
async def regular_user(db: AsyncSession) -> User:
    user = User(
        email="regular@example.com",
        hashed_password=get_password_hash("pw"),
        full_name="Regular",
        is_active=True,
        is_superuser=False,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


# ---------------------------------------------------------------------------
# FastAPI test app factory
# ---------------------------------------------------------------------------


def _make_app(db_session: AsyncSession, current_user: User) -> FastAPI:
    """Build a minimal FastAPI app with the gmail router and overridden deps."""
    app = FastAPI()
    app.include_router(gmail_router)

    async def _override_db():
        yield db_session

    async def _override_active_user():
        return current_user

    async def _override_superuser():
        from fastapi import HTTPException
        if not current_user.is_superuser and getattr(current_user, "role", "") != "admin":
            raise HTTPException(status_code=403, detail="Not enough privileges")
        return current_user

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_active_user] = _override_active_user
    app.dependency_overrides[get_current_superuser] = _override_superuser
    return app


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestRelinkAuth:
    @pytest.mark.asyncio
    async def test_non_admin_gets_403(self, db: AsyncSession, regular_user: User):
        """Non-admin user must receive 403 from the relink endpoint."""
        app = _make_app(db, regular_user)
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post("/api/integrations/gmail/relink", json={})
        assert resp.status_code == 403


class TestRelinkEmailQueue:
    @pytest.mark.asyncio
    async def test_null_entity_with_cc_contact_gets_linked(
        self, db: AsyncSession, admin_user: User
    ):
        """EmailQueue row with NULL entity_id whose CC contains a contact email is linked."""
        contact = Contact(
            email="contact@client.com",
            first_name="CC",
            last_name="Contact",
            owner_id=admin_user.id,
            created_by_id=admin_user.id,
        )
        db.add(contact)
        await db.commit()
        await db.refresh(contact)

        row = EmailQueue(
            to_email="someone@other.com",
            from_email="sender@example.com",
            cc="Display Name <contact@client.com>",
            subject="Test",
            body="body",
            status="sent",
            sent_via="gmail",
            sent_by_id=admin_user.id,
        )
        db.add(row)
        await db.commit()
        await db.refresh(row)

        app = _make_app(db, admin_user)
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post("/api/integrations/gmail/relink", json={})

        assert resp.status_code == 200
        data = resp.json()
        assert data["linked"] == 1
        assert data["scanned"] >= 1
        assert data["dry_run"] is False

        await db.refresh(row)
        assert row.entity_type == "contacts"
        assert row.entity_id == contact.id

    @pytest.mark.asyncio
    async def test_already_linked_row_not_touched(
        self, db: AsyncSession, admin_user: User
    ):
        """EmailQueue row with a non-NULL entity_id must not be overwritten."""
        contact = Contact(
            email="existing@client.com",
            first_name="Existing",
            last_name="Link",
            owner_id=admin_user.id,
            created_by_id=admin_user.id,
        )
        db.add(contact)
        await db.commit()
        await db.refresh(contact)

        row = EmailQueue(
            to_email="existing@client.com",
            from_email="sender@example.com",
            subject="Already linked",
            body="body",
            status="sent",
            sent_via="gmail",
            sent_by_id=admin_user.id,
            entity_type="contacts",
            entity_id=contact.id,
        )
        db.add(row)
        await db.commit()
        await db.refresh(row)
        original_entity_id = row.entity_id

        app = _make_app(db, admin_user)
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post("/api/integrations/gmail/relink", json={})

        assert resp.status_code == 200
        data = resp.json()
        # Row with entity_id set is excluded by the WHERE clause — not scanned.
        assert data["linked"] == 0

        await db.refresh(row)
        assert row.entity_id == original_entity_id

    @pytest.mark.asyncio
    async def test_no_matching_contact_row_is_skipped(
        self, db: AsyncSession, admin_user: User
    ):
        """EmailQueue row whose addresses match no contact must be skipped (not linked)."""
        row = EmailQueue(
            to_email="unknown@nowhere.com",
            from_email="also@unknown.com",
            subject="No match",
            body="body",
            status="sent",
            sent_via="gmail",
            sent_by_id=admin_user.id,
        )
        db.add(row)
        await db.commit()

        app = _make_app(db, admin_user)
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post("/api/integrations/gmail/relink", json={})

        assert resp.status_code == 200
        data = resp.json()
        assert data["linked"] == 0
        assert data["skipped"] >= 1

        await db.refresh(row)
        assert row.entity_id is None

    @pytest.mark.asyncio
    async def test_dry_run_does_not_write(
        self, db: AsyncSession, admin_user: User
    ):
        """dry_run=True must leave entity_id NULL even when a match is found."""
        contact = Contact(
            email="dryrun@client.com",
            first_name="Dry",
            last_name="Run",
            owner_id=admin_user.id,
            created_by_id=admin_user.id,
        )
        db.add(contact)
        await db.commit()
        await db.refresh(contact)

        row = EmailQueue(
            to_email="dryrun@client.com",
            from_email="sender@example.com",
            subject="Dry run test",
            body="body",
            status="sent",
            sent_via="gmail",
            sent_by_id=admin_user.id,
        )
        db.add(row)
        await db.commit()
        await db.refresh(row)

        app = _make_app(db, admin_user)
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                "/api/integrations/gmail/relink", json={"dry_run": True}
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["dry_run"] is True
        assert data["linked"] == 1  # match found…

        # …but no DB write made.
        await db.refresh(row)
        assert row.entity_id is None


class TestRelinkSelfAddressExclusion:
    @pytest.mark.asyncio
    async def test_self_address_in_participants_does_not_link_to_self_card(
        self, db: AsyncSession, admin_user: User
    ):
        """A row whose participant list contains a GmailConnection's primary
        or alias must not link to a contact card that owns that address —
        same pollution PR #202 fixed for the live sync path. The matcher
        sees only the third-party addresses, so the row stays unlinked
        when no other participant matches.
        """
        from src.integrations.gmail.models import GmailConnection
        from src.email.models import InboundEmail

        # Connection-owner's mailbox
        conn = GmailConnection(
            user_id=admin_user.id,
            email="accounting@linkcreativeco.com",
            aliases=["giancarlo@linkcreativeco.com"],
            access_token="t",
            refresh_token="t",
            token_expiry=None,
            scopes="",
        )
        db.add(conn)

        # A self-contact for the connection-owner exists (the pollution
        # case): if relink doesn't exclude self-addresses, it would link
        # the inbound row to THIS contact instead of leaving it unlinked.
        self_contact = Contact(
            email="accounting@linkcreativeco.com",
            first_name="Giancarlo",
            last_name="Self",
            owner_id=admin_user.id,
            created_by_id=admin_user.id,
        )
        db.add(self_contact)
        await db.commit()
        await db.refresh(conn)
        await db.refresh(self_contact)

        # Inbound row: from a third party (no contact card for them) to
        # the connection's address. participant_emails is auto-populated
        # by the model listener.
        row = InboundEmail(
            resend_email_id="gmail:abc123",
            from_email="stranger@example.com",
            to_email="accounting@linkcreativeco.com",
            subject="hi",
            received_at=__import__("datetime").datetime(2026, 5, 1, tzinfo=__import__("datetime").timezone.utc),
        )
        db.add(row)
        await db.commit()
        await db.refresh(row)

        app = _make_app(db, admin_user)
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post("/api/integrations/gmail/relink", json={})

        assert resp.status_code == 200
        await db.refresh(row)
        # Self-address excluded; no contact for stranger@; row stays NULL.
        assert row.entity_id is None
        assert row.entity_type is None

    @pytest.mark.asyncio
    async def test_self_address_excluded_but_third_party_still_links(
        self, db: AsyncSession, admin_user: User
    ):
        """Counterpart: the self-exclude must NOT mask a real contact
        match. An inbound CC'd to the connection's alias AND to a real
        contact should still link to the real contact.
        """
        from src.integrations.gmail.models import GmailConnection
        from src.email.models import InboundEmail

        conn = GmailConnection(
            user_id=admin_user.id,
            email="accounting@linkcreativeco.com",
            aliases=["giancarlo@linkcreativeco.com"],
            access_token="t",
            refresh_token="t",
            token_expiry=None,
            scopes="",
        )
        db.add(conn)

        target = Contact(
            email="customer@example.com",
            first_name="Real",
            last_name="Customer",
            owner_id=admin_user.id,
            created_by_id=admin_user.id,
        )
        db.add(target)
        await db.commit()
        await db.refresh(target)

        row = InboundEmail(
            resend_email_id="gmail:def456",
            from_email="customer@example.com",
            to_email="accounting@linkcreativeco.com",
            cc="giancarlo@linkcreativeco.com",
            subject="thread",
            received_at=__import__("datetime").datetime(2026, 5, 1, tzinfo=__import__("datetime").timezone.utc),
        )
        db.add(row)
        await db.commit()
        await db.refresh(row)

        app = _make_app(db, admin_user)
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post("/api/integrations/gmail/relink", json={})

        assert resp.status_code == 200
        await db.refresh(row)
        assert row.entity_type == "contacts"
        assert row.entity_id == target.id
