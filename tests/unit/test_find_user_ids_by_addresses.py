"""Unit tests for find_user_ids_by_addresses helper."""

import os
import sys
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "backend"))

from src.database import Base
from src.auth.models import User
from src.auth.security import get_password_hash
from src.integrations.gmail.models import GmailConnection


TEST_DB_URL = "sqlite+aiosqlite:///:memory:"


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


async def _make_user(db: AsyncSession, email: str) -> User:
    user = User(
        email=email,
        hashed_password=get_password_hash("pw"),
        full_name=email.split("@")[0],
        is_active=True,
        is_superuser=False,
    )
    db.add(user)
    await db.flush()
    return user


async def _make_connection(
    db: AsyncSession,
    user_id: int,
    email: str,
    *,
    revoked: bool = False,
) -> GmailConnection:
    conn = GmailConnection(
        user_id=user_id,
        email=email,
        access_token="tok",
        scopes="https://mail.google.com/",
        revoked_at=datetime.now(timezone.utc) if revoked else None,
    )
    db.add(conn)
    await db.flush()
    return conn


class TestFindUserIdsByAddresses:
    @pytest.mark.asyncio
    async def test_returns_matching_user(self, db: AsyncSession):
        """Should return user_id when primary email matches."""
        user = await _make_user(db, "alice@example.com")
        await _make_connection(db, user.id, "alice@example.com")
        await db.commit()

        from src.email.participants import find_user_ids_by_addresses

        result = await find_user_ids_by_addresses(db, ["alice@example.com"])
        assert user.id in result

    @pytest.mark.asyncio
    async def test_case_insensitive_match(self, db: AsyncSession):
        """Should match regardless of address casing."""
        user = await _make_user(db, "bob@example.com")
        await _make_connection(db, user.id, "bob@example.com")
        await db.commit()

        from src.email.participants import find_user_ids_by_addresses

        result = await find_user_ids_by_addresses(db, ["BOB@EXAMPLE.COM"])
        assert user.id in result

    @pytest.mark.asyncio
    async def test_no_match_returns_empty(self, db: AsyncSession):
        """Should return empty list when no connections match."""
        user = await _make_user(db, "carol@example.com")
        await _make_connection(db, user.id, "carol@example.com")
        await db.commit()

        from src.email.participants import find_user_ids_by_addresses

        result = await find_user_ids_by_addresses(db, ["nobody@example.com"])
        assert result == []

    @pytest.mark.asyncio
    async def test_empty_addresses_returns_empty(self, db: AsyncSession):
        """Should short-circuit and return empty for empty address list."""
        from src.email.participants import find_user_ids_by_addresses

        result = await find_user_ids_by_addresses(db, [])
        assert result == []

    @pytest.mark.asyncio
    async def test_revoked_connection_excluded(self, db: AsyncSession):
        """Should not return user whose only connection is revoked."""
        user = await _make_user(db, "dave@example.com")
        await _make_connection(db, user.id, "dave@example.com", revoked=True)
        await db.commit()

        from src.email.participants import find_user_ids_by_addresses

        result = await find_user_ids_by_addresses(db, ["dave@example.com"])
        assert user.id not in result

    @pytest.mark.asyncio
    async def test_multiple_matches(self, db: AsyncSession):
        """Should return all matching user_ids when multiple users match."""
        u1 = await _make_user(db, "eve@example.com")
        u2 = await _make_user(db, "frank@example.com")
        await _make_connection(db, u1.id, "eve@example.com")
        await _make_connection(db, u2.id, "frank@example.com")
        await db.commit()

        from src.email.participants import find_user_ids_by_addresses

        result = await find_user_ids_by_addresses(db, ["eve@example.com", "frank@example.com"])
        assert u1.id in result
        assert u2.id in result

    @pytest.mark.asyncio
    async def test_partial_match_only_returns_matched(self, db: AsyncSession):
        """Should only return users whose address appears in the list."""
        u1 = await _make_user(db, "grace@example.com")
        u2 = await _make_user(db, "heidi@example.com")
        await _make_connection(db, u1.id, "grace@example.com")
        await _make_connection(db, u2.id, "heidi@example.com")
        await db.commit()

        from src.email.participants import find_user_ids_by_addresses

        result = await find_user_ids_by_addresses(db, ["grace@example.com"])
        assert u1.id in result
        assert u2.id not in result
