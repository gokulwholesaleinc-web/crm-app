"""Unit tests for find_contact_id_by_any_email helper."""

import os
import sys
from datetime import datetime, timezone

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "backend"))

from src.database import Base
from src.auth.models import User
from src.contacts.models import Contact, ContactEmailAlias
from src.contacts.alias_match import find_contact_id_by_any_email
from ._engine import is_postgres, make_test_engine


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


@pytest_asyncio.fixture
async def user(db: AsyncSession) -> User:
    from src.auth.security import get_password_hash
    u = User(
        email="owner@example.com",
        hashed_password=get_password_hash("pw"),
        full_name="Owner",
        is_active=True,
        is_superuser=False,
    )
    db.add(u)
    await db.commit()
    await db.refresh(u)
    return u


@pytest_asyncio.fixture
async def contact(db: AsyncSession, user: User) -> Contact:
    c = Contact(
        first_name="Alice",
        last_name="Smith",
        email="alice@primary.com",
        owner_id=user.id,
        created_by_id=user.id,
    )
    db.add(c)
    await db.commit()
    await db.refresh(c)
    return c


class TestFindContactIdByAnyEmail:
    @pytest.mark.asyncio
    async def test_matches_primary_email(self, contact: Contact, db: AsyncSession):
        entity_type, entity_id = await find_contact_id_by_any_email(
            ["alice@primary.com"], db
        )
        assert entity_type == "contacts"
        assert entity_id == contact.id

    @pytest.mark.asyncio
    async def test_matches_alias_email_case_insensitive(
        self, contact: Contact, db: AsyncSession
    ):
        alias = ContactEmailAlias(
            contact_id=contact.id,
            email="Alice.Work@Company.com",
            label="Work",
        )
        db.add(alias)
        await db.commit()

        entity_type, entity_id = await find_contact_id_by_any_email(
            ["alice.work@company.com"], db
        )
        assert entity_type == "contacts"
        assert entity_id == contact.id

    @pytest.mark.asyncio
    async def test_returns_first_match_in_input_order(
        self, db: AsyncSession, user: User
    ):
        c1 = Contact(
            first_name="Bob", last_name="One", email="bob1@example.com",
            owner_id=user.id, created_by_id=user.id,
        )
        c2 = Contact(
            first_name="Carol", last_name="Two", email="carol2@example.com",
            owner_id=user.id, created_by_id=user.id,
        )
        db.add_all([c1, c2])
        await db.commit()
        await db.refresh(c1)
        await db.refresh(c2)

        # c2's address appears first in input list — must win
        entity_type, entity_id = await find_contact_id_by_any_email(
            ["carol2@example.com", "bob1@example.com"], db
        )
        assert entity_type == "contacts"
        assert entity_id == c2.id

    @pytest.mark.asyncio
    async def test_skips_soft_deleted_contacts(
        self, db: AsyncSession, user: User
    ):
        deleted = Contact(
            first_name="Deleted", last_name="Guy", email="deleted@example.com",
            owner_id=user.id, created_by_id=user.id,
            deleted_at=datetime.now(timezone.utc),
        )
        db.add(deleted)
        await db.commit()

        entity_type, entity_id = await find_contact_id_by_any_email(
            ["deleted@example.com"], db
        )
        assert entity_type is None
        assert entity_id is None

    @pytest.mark.asyncio
    async def test_returns_none_when_no_match(self, db: AsyncSession):
        entity_type, entity_id = await find_contact_id_by_any_email(
            ["nobody@nowhere.com"], db
        )
        assert entity_type is None
        assert entity_id is None

    @pytest.mark.asyncio
    async def test_empty_list_returns_none(self, db: AsyncSession):
        entity_type, entity_id = await find_contact_id_by_any_email([], db)
        assert entity_type is None
        assert entity_id is None

    @pytest.mark.asyncio
    async def test_alias_on_deleted_contact_not_matched(
        self, db: AsyncSession, user: User
    ):
        deleted = Contact(
            first_name="Gone", last_name="User", email="gone@example.com",
            owner_id=user.id, created_by_id=user.id,
            deleted_at=datetime.now(timezone.utc),
        )
        db.add(deleted)
        await db.commit()
        await db.refresh(deleted)

        alias = ContactEmailAlias(
            contact_id=deleted.id,
            email="gone-alias@example.com",
        )
        db.add(alias)
        await db.commit()

        entity_type, entity_id = await find_contact_id_by_any_email(
            ["gone-alias@example.com"], db
        )
        assert entity_type is None
        assert entity_id is None
