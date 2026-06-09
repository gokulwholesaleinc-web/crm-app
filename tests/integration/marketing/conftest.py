"""Real-Postgres test tier for the marketing warehouse (C1).

The default unit harness is in-memory SQLite, which silently ignores
``NULLS NOT DISTINCT``, ``ON CONFLICT``, ``pg_advisory_xact_lock`` and JSONB — the
exact correctness machinery the warehouse depends on (C1). Tests in this package
therefore run against a real Postgres 15+ given by ``MARKETING_TEST_PG_URL`` (a
disposable Docker ``postgres:16`` locally, or a Neon branch in CI). When the env
var is unset the whole tier is skipped, so the SQLite gate stays green offline.

The root ``tests/conftest.py`` has already imported every CRM model onto ``Base``
(including ``marketing``), so ``Base.metadata.create_all`` here builds the full
schema — the marketing tables plus their ``companies``/``users`` parents — exactly
as a real deploy's migrations would. Each test gets a clean slate via
``TRUNCATE … RESTART IDENTITY CASCADE`` over the marketing tables.
"""

from __future__ import annotations

import os
from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool
from src.database import Base

PG_URL = os.getenv("MARKETING_TEST_PG_URL")

# C2: in CI the real-PG tier is mandatory — MARKETING_REQUIRE_PG=1 turns a missing
# URL into a hard FAILURE instead of a silent skip, so the Cluster-A acceptance gate
# can never green-because-absent again. Locally (flag unset) it still skips offline.
_REQUIRE_PG = os.getenv("MARKETING_REQUIRE_PG", "").strip().lower() in ("1", "true", "yes")

# Child-before-parent so CASCADE truncation never trips an FK mid-statement.
_MARKETING_TABLES = (
    "fx_rates",
    "marketing_alerts",
    "marketing_report_schedules",
    "budget_periods",
    "marketing_credential_audit",
    "marketing_sync_runs",
    "site_health_snapshots",
    "analytics_daily",
    "ads_daily_metrics",
    "marketing_raw_payloads",
    "marketing_ad_groups",
    "marketing_campaigns",
    "platform_connections",
)


# Built once per session, but against the real (persistent) DB so a mutable
# sentinel — not a session-scoped fixture — carries the "already built" state. A
# function-scoped engine with NullPool means no pooled asyncpg connection ever
# outlives the per-test event loop (pytest-asyncio gives each test its own loop),
# which is the whole reason a session-scoped async engine corrupts here.
_schema_built: set[bool] = set()


@pytest_asyncio.fixture
async def pg_engine():
    """Per-test engine (NullPool) against the real-PG tier; schema built once."""
    if not PG_URL:
        if _REQUIRE_PG:
            pytest.fail(
                "MARKETING_TEST_PG_URL is unset but MARKETING_REQUIRE_PG is on — the "
                "real-Postgres C2 acceptance gate must run in CI, never silently skip."
            )
        pytest.skip("MARKETING_TEST_PG_URL not set — real-Postgres tier skipped")
    engine = create_async_engine(PG_URL, poolclass=NullPool)
    if not _schema_built:
        # drop_all THEN create_all: a persistent test DB (the local Docker
        # postgres, reused across runs) can hold a STALE schema that create_all's
        # checkfirst would never correct — e.g. a grain index created before A2 was
        # finalized, missing NULLS NOT DISTINCT, silently breaking de-dup (H5).
        # Rebuilding from scratch guarantees the schema always matches the model;
        # the C2 gate then exercises the real DDL, not whatever was left behind.
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
            await conn.run_sync(Base.metadata.create_all)
        _schema_built.add(True)
    try:
        yield engine
    finally:
        await engine.dispose()


@pytest_asyncio.fixture
async def pg_session(pg_engine) -> AsyncGenerator[AsyncSession, None]:
    """Function-scoped session on a freshly truncated marketing schema."""
    async with pg_engine.begin() as conn:
        await conn.exec_driver_sql(
            "TRUNCATE TABLE "
            + ", ".join(_MARKETING_TABLES)
            + " RESTART IDENTITY CASCADE"
        )
    maker = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with maker() as session:
        yield session
