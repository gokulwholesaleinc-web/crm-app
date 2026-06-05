"""Migration-vs-model parity for the bundle tables (migration 055).

The plan (§3/B3) notes the SQLite unit harness builds the schema with
``create_all`` and never runs the Alembic migration — so model/migration drift
(a forgotten index, a constraint named differently) would slip through. This
test closes that gap WITHOUT a Postgres dependency: it executes migration 055's
``upgrade()`` against SQLite (via Alembic's ``Operations`` API) and diffs the
resulting schema against a fresh ``create_all`` of the same two tables — every
column, the PK name, and every unique/index/FK (name + columns + referent) must
match. ``downgrade()`` is exercised too.

This is NOT a substitute for running the real migration on Postgres before
deploy (SQLite still ignores ON DELETE CASCADE + the 63-char identifier cap) —
it catches DDL drift, which is the failure mode the SQLite harness otherwise
hides.
"""

import importlib.util
from pathlib import Path

import src.onboarding.models  # noqa: F401 — register the bundle models on Base
from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext
from sqlalchemy import create_engine, inspect
from src.database import Base

_BUNDLE_TABLES = (
    "onboarding_template_bundles",
    "onboarding_template_bundle_items",
)

_MIGRATION_PATH = (
    Path(__file__).resolve().parents[2]
    / "backend"
    / "alembic"
    / "versions"
    / "055_onboarding_bundles.py"
)


def _load_migration():
    spec = importlib.util.spec_from_file_location("mig055", _MIGRATION_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


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
            (
                fk["name"],
                tuple(fk["constrained_columns"]),
                fk["referred_table"],
            )
            for fk in inspector.get_foreign_keys(table)
        ),
    }


def test_migration_055_matches_create_all():
    """Running migration 055 yields the same DDL as create_all for both tables."""
    # Reference schema: a plain create_all.
    ref_engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(ref_engine)
    ref_insp = inspect(ref_engine)
    reference = {t: _snapshot(ref_insp, t) for t in _BUNDLE_TABLES}

    # Candidate schema: create_all everything, drop the two bundle tables, then
    # rebuild them via the migration's upgrade().
    mig = _load_migration()
    mig_engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(mig_engine)
    with mig_engine.connect() as conn:
        # Drop child-first (items references bundles).
        conn.exec_driver_sql("DROP TABLE onboarding_template_bundle_items")
        conn.exec_driver_sql("DROP TABLE onboarding_template_bundles")
        ctx = MigrationContext.configure(conn)
        with Operations.context(ctx):
            mig.upgrade()
        mig_insp = inspect(conn)
        candidate = {t: _snapshot(mig_insp, t) for t in _BUNDLE_TABLES}

    for table in _BUNDLE_TABLES:
        assert candidate[table] == reference[table], (
            f"migration 055 drifted from create_all for {table}: "
            f"{candidate[table]} != {reference[table]}"
        )


def test_migration_055_downgrade_drops_tables():
    """downgrade() removes both bundle tables (round-trip)."""
    mig = _load_migration()
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with engine.connect() as conn:
        conn.exec_driver_sql("DROP TABLE onboarding_template_bundle_items")
        conn.exec_driver_sql("DROP TABLE onboarding_template_bundles")
        ctx = MigrationContext.configure(conn)
        with Operations.context(ctx):
            mig.upgrade()
            assert set(_BUNDLE_TABLES).issubset(set(inspect(conn).get_table_names()))
            mig.downgrade()
        remaining = set(inspect(conn).get_table_names())
    assert not set(_BUNDLE_TABLES).intersection(remaining)
