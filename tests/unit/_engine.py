"""Shared test-engine factory.

The new ``inbound_emails.participant_emails`` ARRAY column doesn't compile
on SQLite, so any test that mounts the schema needs to either default to
the env's Postgres (CI provisions one via service container) or fall back
to in-memory SQLite for offline local runs.

Each unit test that builds its own engine should call ``make_test_engine()``
instead of hand-rolling a `create_async_engine(...)`.
"""

from __future__ import annotations

import os

from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.pool import StaticPool

DEFAULT_TEST_DB_URL = "sqlite+aiosqlite:///:memory:"


def get_test_db_url() -> str:
    return os.environ.get("DATABASE_URL", DEFAULT_TEST_DB_URL)


def is_postgres(url: str | None = None) -> bool:
    return (url or get_test_db_url()).startswith("postgresql")


def make_test_engine() -> AsyncEngine:
    """Return an AsyncEngine pointed at the test database.

    Postgres path drops StaticPool/check_same_thread (SQLite-only knobs).
    Caller is responsible for `metadata.create_all` (and, on Postgres,
    enabling pgvector if vector columns are referenced — see
    ``tests/conftest.py::test_engine``).
    """
    url = get_test_db_url()
    if is_postgres(url):
        return create_async_engine(url, echo=False)
    return create_async_engine(
        url,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        echo=False,
    )
