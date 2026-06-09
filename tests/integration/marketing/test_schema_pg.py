"""Real-Postgres schema assertions (H5) — the A2 NULLS NOT DISTINCT DDL.

The SQLite migration-parity test (``tests/unit/test_marketing_migration.py``) can
NOT see ``NULLS NOT DISTINCT`` — SQLite silently drops the
``postgresql_nulls_not_distinct`` kwarg, and the structural snapshot only captures
column/index/constraint names. So a dropped-or-typo'd kwarg in the model or the
migration would ship a duplicate-causing constraint with every test green. This
test runs on the real-PG tier and asserts the actual semantics: the four grain
unique indexes MUST be ``NULLS NOT DISTINCT`` (``pg_index.indnullsnotdistinct``,
PG15+), so an account-level row with NULL campaign/adgroup ids de-dups on re-run.
"""

from __future__ import annotations

import pytest
from sqlalchemy import text

pytestmark = pytest.mark.pg

# The four grain uniques that MUST be NULLS NOT DISTINCT (A2). ads_daily_metrics is
# the load-bearing one (account rows carry NULL campaign/adgroup ids); the others
# de-dup on a re-fetch of the same window.
_NULLS_NOT_DISTINCT_INDEXES = (
    "uq_ads_daily_metrics_grain",
    "uq_analytics_daily_grain",
    "uq_site_health_snapshots_grain",
    "uq_marketing_raw_payloads_key",
)


async def test_grain_indexes_are_nulls_not_distinct(pg_session):
    """Every grain unique index is NULLS NOT DISTINCT on real Postgres (A2 / H5)."""
    rows = (
        await pg_session.execute(
            text(
                """
                SELECT i.relname AS index_name, ix.indnullsnotdistinct
                FROM pg_index ix
                JOIN pg_class i ON i.oid = ix.indexrelid
                WHERE i.relname = ANY(:names)
                """
            ),
            {"names": list(_NULLS_NOT_DISTINCT_INDEXES)},
        )
    ).all()

    found = {name: bool(flag) for name, flag in rows}
    missing = [n for n in _NULLS_NOT_DISTINCT_INDEXES if n not in found]
    assert not missing, f"grain index(es) not present on PG: {missing}"
    not_nnd = [n for n, flag in found.items() if not flag]
    assert not not_nnd, (
        "grain index(es) are NOT NULLS NOT DISTINCT (A2 broken → account-level "
        f"NULL-key rows would duplicate on re-run): {not_nnd}"
    )
