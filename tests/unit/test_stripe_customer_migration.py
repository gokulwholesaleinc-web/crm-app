"""StripeCustomer company merge-chain migration semantics."""

import importlib.util
from pathlib import Path

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
