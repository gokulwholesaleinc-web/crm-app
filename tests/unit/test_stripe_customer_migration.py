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


def test_company_customer_plan_refuses_multiple_live_rows():
    keep_id, loser_ids, skip_reason = migration._company_customer_coalesce_plan(
        [
            {
                "id": 10,
                "created_at": "2026-01-01T00:00:00Z",
                "active_subscription_count": 1,
                "payment_count": 0,
            },
            {
                "id": 20,
                "created_at": "2026-02-01T00:00:00Z",
                "active_subscription_count": 0,
                "payment_count": 1,
            },
        ]
    )

    assert keep_id is None
    assert loser_ids == []
    assert skip_reason == "multiple StripeCustomer rows have live billing links"


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
                "stripe_customer_id TEXT, "
                "created_at TEXT)"
            )
        )
        conn.execute(
            sa.text("CREATE TABLE payments (id INTEGER PRIMARY KEY, customer_id INTEGER)")
        )
        conn.execute(
            sa.text(
                "CREATE TABLE subscriptions ("
                "id INTEGER PRIMARY KEY, "
                "customer_id INTEGER, "
                "status TEXT)"
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
                "(id, company_id, contact_id, stripe_customer_id, created_at) VALUES "
                "(10, 2, NULL, 'cus_live_older', '2026-01-01T00:00:00Z'), "
                "(20, 1, NULL, 'cus_empty_newer', '2026-02-01T00:00:00Z'), "
                "(30, 1, 99, 'cus_contact_linked', '2026-03-01T00:00:00Z')"
            )
        )
        conn.execute(
            sa.text(
                "INSERT INTO payments (id, customer_id) VALUES (100, 10)"
            )
        )
        conn.execute(
            sa.text(
                "INSERT INTO subscriptions (id, customer_id, status) VALUES "
                "(200, 10, 'active')"
            )
        )

        monkeypatch.setattr(migration.op, "get_bind", lambda: conn)
        migration.upgrade()

        customer_rows = conn.execute(
            sa.text(
                "SELECT id, company_id, contact_id, stripe_customer_id "
                "FROM stripe_customers ORDER BY id"
            )
        ).mappings().all()
        assert [dict(row) for row in customer_rows] == [
            {
                "id": 10,
                "company_id": 2,
                "contact_id": None,
                "stripe_customer_id": "cus_live_older",
            },
            {
                "id": 20,
                "company_id": None,
                "contact_id": None,
                "stripe_customer_id": "cus_empty_newer",
            },
            {
                "id": 30,
                "company_id": 2,
                "contact_id": 99,
                "stripe_customer_id": "cus_contact_linked",
            },
        ]

        payment_customer_ids = conn.execute(
            sa.text("SELECT customer_id FROM payments ORDER BY id")
        ).scalars().all()
        subscription_customer_ids = conn.execute(
            sa.text("SELECT customer_id FROM subscriptions ORDER BY id")
        ).scalars().all()
        assert payment_customer_ids == [10]
        assert subscription_customer_ids == [10]


def test_upgrade_coalesces_duplicates_already_on_live_company(monkeypatch):
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
                "stripe_customer_id TEXT, "
                "created_at TEXT)"
            )
        )
        conn.execute(
            sa.text("CREATE TABLE payments (id INTEGER PRIMARY KEY, customer_id INTEGER)")
        )
        conn.execute(
            sa.text(
                "CREATE TABLE subscriptions ("
                "id INTEGER PRIMARY KEY, "
                "customer_id INTEGER, "
                "status TEXT)"
            )
        )
        conn.execute(
            sa.text("INSERT INTO companies (id, status, merged_into_id) VALUES (2, 'customer', NULL)")
        )
        conn.execute(
            sa.text(
                "INSERT INTO stripe_customers "
                "(id, company_id, contact_id, stripe_customer_id, created_at) VALUES "
                "(10, 2, NULL, 'cus_same_live_older', '2026-01-01T00:00:00Z'), "
                "(20, 2, NULL, 'cus_same_empty_newer', '2026-02-01T00:00:00Z')"
            )
        )
        conn.execute(
            sa.text(
                "INSERT INTO subscriptions (id, customer_id, status) VALUES "
                "(200, 10, 'active')"
            )
        )

        monkeypatch.setattr(migration.op, "get_bind", lambda: conn)
        migration.upgrade()

        customer_rows = conn.execute(
            sa.text(
                "SELECT id, company_id, contact_id, stripe_customer_id "
                "FROM stripe_customers ORDER BY id"
            )
        ).mappings().all()
        assert [dict(row) for row in customer_rows] == [
            {
                "id": 10,
                "company_id": 2,
                "contact_id": None,
                "stripe_customer_id": "cus_same_live_older",
            },
            {
                "id": 20,
                "company_id": None,
                "contact_id": None,
                "stripe_customer_id": "cus_same_empty_newer",
            },
        ]

        subscription_customer_ids = conn.execute(
            sa.text("SELECT customer_id FROM subscriptions ORDER BY id")
        ).scalars().all()
        assert subscription_customer_ids == [10]
