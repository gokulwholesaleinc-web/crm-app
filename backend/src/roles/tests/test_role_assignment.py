from __future__ import annotations

import os
import sys
import time
from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../../"))

from src.auth.dependencies import _user_cache
from src.auth.models import User
from src.core.data_scope import _scope_cache
from src.database import Base
from src.roles.models import Role, RoleName, UserRole
from src.roles.service import RoleService

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(
            Base.metadata.create_all,
            tables=[User.__table__, Role.__table__, UserRole.__table__],
        )

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session
        await session.rollback()
    await engine.dispose()


@pytest_asyncio.fixture(autouse=True)
def clear_role_related_caches():
    _user_cache.clear()
    _scope_cache.clear()
    yield
    _user_cache.clear()
    _scope_cache.clear()


async def test_assign_role_syncs_user_column_and_invalidates_caches(
    db_session: AsyncSession,
):
    manager_role = Role(name=RoleName.MANAGER.value, permissions={})
    sales_role = Role(name=RoleName.SALES_REP.value, permissions={})
    user = User(
        email="rep@example.test",
        hashed_password="hash",
        full_name="Sales Rep",
        is_active=True,
        is_approved=True,
        role=RoleName.SALES_REP.value,
    )
    db_session.add_all([manager_role, sales_role, user])
    await db_session.flush()
    db_session.add(UserRole(user_id=user.id, role_id=sales_role.id))
    await db_session.commit()

    _user_cache[user.id] = user
    _scope_cache[user.id] = (time.monotonic(), object())

    assigned = await RoleService(db_session).assign_role_to_user(user.id, manager_role.id)
    await db_session.commit()

    await db_session.refresh(user)
    assert user.role == RoleName.MANAGER.value
    assert assigned.role_id == manager_role.id
    assert _user_cache.get(user.id) is None
    assert user.id not in _scope_cache

    result = await db_session.execute(select(UserRole).where(UserRole.user_id == user.id))
    rows = list(result.scalars().all())
    assert len(rows) == 1
    assert rows[0].role_id == manager_role.id
