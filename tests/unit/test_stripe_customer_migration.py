"""StripeCustomer company merge-chain migration semantics."""

import importlib.util
from pathlib import Path

import sqlalchemy as sa

_MIGRATION = (
    Path(__file__).resolve().parents[2]
    / "backend"
    / "alembic"
    / "versions"
    / "060_stripe_customer_live_root.py"
)

spec = importlib.util.spec_from_file_location("migration_060_stripe_customer_live_root", _MIGRATION)
assert spec is not None
migration = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(migration)


def test_live_root_follows_multi_hop_merge_chain():
    companies = {
        1: {"status": "merged", "merged_into_id": 2},
        2: {"status": "merged", "merged_into_id": 3},
        3: {"status": "customer", "merged_into_id": None},
    }

    assert migration._live_root(1, companies) == 3


def test_live_root_leaves_broken_or_cyclic_chains_unresolved():
    broken = {
        1: {"status": "merged", "merged_into_id": 999},
    }
    cyclic = {
        1: {"status": "merged", "merged_into_id": 2},
        2: {"status": "merged", "merged_into_id": 1},
    }

    assert migration._live_root(1, broken) is None
    assert migration._live_root(1, cyclic) is None


def test_upgrade_coalesces_company_owned_customer_duplicates(monkeypatch):
    engine = sa.create_engine("sqlite://")
    with engine.begin() as conn:
        conn.execute(
            sa.text(
                "CREATE TABLE companies ("
                "id INTEGER PRIMARY KEY, "
                "status VARCHAR(20), "
                "merged_into_id INTEGER)"
            )
        )
        conn.execute(
            sa.text(
                "CREATE TABLE stripe_customers ("
                "id INTEGER PRIMARY KEY, "
                "company_id INTEGER, "
                "contact_id INTEGER, "
                "created_at TEXT)"
            )
        )
        conn.execute(
            sa.text("CREATE TABLE payments (id INTEGER PRIMARY KEY, customer_id INTEGER)")
        )
        conn.execute(
            sa.text(
                "CREATE TABLE subscriptions (id INTEGER PRIMARY KEY, customer_id INTEGER)"
            )
        )
        conn.execute(
            sa.text(
                "INSERT INTO companies (id, status, merged_into_id) VALUES "
                "(1, 'merged', 2), "
                "(2, 'customer', NULL)"
            )
        )
        conn.execute(
            sa.text(
                "INSERT INTO stripe_customers "
                "(id, company_id, contact_id, created_at) VALUES "
                "(10, 2, NULL, '2026-01-01T00:00:00Z'), "
                "(20, 1, NULL, '2026-02-01T00:00:00Z'), "
                "(30, 1, 99, '2026-03-01T00:00:00Z')"
            )
        )
        conn.execute(
            sa.text(
                "INSERT INTO payments (id, customer_id) VALUES "
                "(100, 10), "
                "(101, 20)"
            )
        )
        conn.execute(
            sa.text(
                "INSERT INTO subscriptions (id, customer_id) VALUES "
                "(200, 10), "
                "(201, 20)"
            )
        )

        monkeypatch.setattr(migration.op, "get_bind", lambda: conn)
        migration.upgrade()

        customer_rows = conn.execute(
            sa.text(
                "SELECT id, company_id, contact_id FROM stripe_customers ORDER BY id"
            )
        ).mappings().all()
        assert [dict(row) for row in customer_rows] == [
            {"id": 20, "company_id": 2, "contact_id": None},
            {"id": 30, "company_id": 2, "contact_id": 99},
        ]

        payment_customer_ids = conn.execute(
            sa.text("SELECT customer_id FROM payments ORDER BY id")
        ).scalars().all()
        subscription_customer_ids = conn.execute(
            sa.text("SELECT customer_id FROM subscriptions ORDER BY id")
        ).scalars().all()
        assert payment_customer_ids == [20, 20]
        assert subscription_customer_ids == [20, 20]
