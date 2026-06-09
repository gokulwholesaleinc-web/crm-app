"""Migration-vs-model parity for the marketing warehouse (migration 056).

The SQLite unit harness builds the schema with ``create_all`` and never runs the
Alembic migration, so model/migration drift (a forgotten index, a constraint
named differently, a column nullability flip across 13 interlocking tables) would
slip through to a real Postgres deploy. This test closes that gap WITHOUT a
Postgres dependency: it executes migration 056's ``upgrade()`` against SQLite
(via Alembic's ``Operations`` API) and diffs the resulting schema against a fresh
``create_all`` of the same tables — every column (+ nullability), the PK name,
and every unique/index/FK (name + columns + referent) must match. ``downgrade()``
is exercised too.

This is NOT a substitute for the real-Postgres tier (``test_warehouse_c2_pg.py``)
which exercises ``ON CONFLICT … NULLS NOT DISTINCT`` + advisory locks — SQLite
ignores both. It catches DDL drift, the failure mode the SQLite harness hides.
"""

import importlib.util
from pathlib import Path

import src.marketing.models  # noqa: F401 — register the marketing models on Base
from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext
from sqlalchemy import create_engine, inspect
from src.database import Base

# Drop/rebuild order: children before parents (everything → platform_connections;
# report_schedules/alerts → companies). Mirrors the migration's downgrade order.
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

_VERSIONS = Path(__file__).resolve().parents[2] / "backend" / "alembic" / "versions"
_MIGRATION_PATH = _VERSIONS / "056_marketing_warehouse.py"
_MIGRATION_057_PATH = _VERSIONS / "057_marketing_phase2_ga4.py"

# Applied in order to build the full current marketing schema.
_MIGRATION_PATHS = (_MIGRATION_PATH, _MIGRATION_057_PATH)


def _load_migration(path: Path = _MIGRATION_PATH):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_migrations() -> list:
    return [_load_migration(p) for p in _MIGRATION_PATHS]


def _snapshot(inspector, table: str) -> dict:
    """A name-stable structural snapshot for cross-build comparison."""
    return {
        "columns": {
            c["name"]: bool(c["nullable"]) for c in inspector.get_columns(table)
        },
        "pk": inspector.get_pk_constraint(table)["name"],
        "uniques": sorted(
            (u["name"], tuple(u["column_names"]))
            for u in inspector.get_unique_constraints(table)
        ),
        "indexes": sorted(
            (i["name"], tuple(i["column_names"]))
            for i in inspector.get_indexes(table)
        ),
        "fks": sorted(
            (fk["name"], tuple(fk["constrained_columns"]), fk["referred_table"])
            for fk in inspector.get_foreign_keys(table)
        ),
    }


def _drop_marketing(conn) -> None:
    for table in _MARKETING_TABLES:
        conn.exec_driver_sql(f"DROP TABLE {table}")


def test_migration_056_matches_create_all():
    """Running migrations 056→057 yields the same DDL as create_all for all 13 tables."""
    ref_engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(ref_engine)
    ref_insp = inspect(ref_engine)
    reference = {t: _snapshot(ref_insp, t) for t in _MARKETING_TABLES}

    migs = _load_migrations()
    mig_engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(mig_engine)
    with mig_engine.connect() as conn:
        _drop_marketing(conn)
        ctx = MigrationContext.configure(conn)
        with Operations.context(ctx):
            for mig in migs:
                mig.upgrade()
        mig_insp = inspect(conn)
        candidate = {t: _snapshot(mig_insp, t) for t in _MARKETING_TABLES}

    for table in _MARKETING_TABLES:
        assert candidate[table] == reference[table], (
            f"migration 056 drifted from create_all for {table}:\n"
            f"  candidate={candidate[table]}\n  reference={reference[table]}"
        )


def test_migration_056_declares_nulls_not_distinct_on_grain_keys():
    """The 4 grain uniques must carry postgresql_nulls_not_distinct=True (A2 / H5).

    SQLite drops the kwarg and the structural snapshot can't see it, so a dropped/
    typo'd flag in the MIGRATION (even if the model still has it) would ship a
    duplicate-causing constraint with create_all-based tests green. This source-level
    guard closes that migration-only-drift gap; the real-PG introspection test
    (test_schema_pg.py) locks the model side on Postgres.
    """
    source = _MIGRATION_PATH.read_text()
    grain_constraints = (
        "uq_ads_daily_metrics_grain",
        "uq_analytics_daily_grain",
        "uq_site_health_snapshots_grain",
        "uq_marketing_raw_payloads_key",
    )
    for name in grain_constraints:
        # name + the kwarg are declared on the same line in 056.
        line = next(
            (ln for ln in source.splitlines() if f'name="{name}"' in ln),
            None,
        )
        assert line is not None, f"{name} not found in migration 056"
        assert "postgresql_nulls_not_distinct=True" in line, (
            f"{name} is missing postgresql_nulls_not_distinct=True — A2 de-dup would "
            "break on Postgres (account-level NULL-key rows would duplicate)."
        )


def test_migration_056_downgrade_drops_tables():
    """upgrade 056→057 then downgrade 057→056 round-trips cleanly."""
    migs = _load_migrations()
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with engine.connect() as conn:
        _drop_marketing(conn)
        ctx = MigrationContext.configure(conn)
        with Operations.context(ctx):
            for mig in migs:
                mig.upgrade()
            assert set(_MARKETING_TABLES).issubset(set(inspect(conn).get_table_names()))
            for mig in reversed(migs):
                mig.downgrade()
        remaining = set(inspect(conn).get_table_names())
    assert not set(_MARKETING_TABLES).intersection(remaining)
