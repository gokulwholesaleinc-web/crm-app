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
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "backend"))

from src.database import Base, get_db
from src.auth.models import User
from src.auth.security import get_password_hash
from src.contacts.models import Contact
from src.auth.dependencies import get_current_active_user, get_current_superuser
from src.email.models import EmailQueue
from src.integrations.gmail.router import router as gmail_router
from ._engine import is_postgres, make_test_engine

# ---------------------------------------------------------------------------
# DB fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def engine():
    eng = make_test_engine()
    async with eng.begin() as conn:
        if is_postgres():
            await conn.exec_driver_sql("CREATE EXTENSION IF NOT EXISTS vector")
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
