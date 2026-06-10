"""Backfill StripeCustomer company links through merge chains.

Revision ID: 060_stripe_customer_live_root
Revises: 059_marketing_social
Create Date: 2026-06-10
"""

# ruff: noqa: I001
import sqlalchemy as sa
from alembic import op

revision = "060_stripe_customer_live_root"
down_revision = "059_marketing_social"
branch_labels = None
depends_on = None


def _live_root(company_id: int, companies: dict[int, dict[str, object]]) -> int | None:
    """Follow merged_into_id pointers until a live company root is reached."""
    seen: set[int] = set()
    current_id = company_id
    while current_id not in seen:
        seen.add(current_id)
        company = companies.get(current_id)
        if company is None:
            return None
        next_id = company["merged_into_id"]
        if company["status"] != "merged" and next_id is None:
            return current_id
        if next_id is None:
            return None
        current_id = int(next_id)
    return None


def upgrade() -> None:
    conn = op.get_bind()
    company_rows = conn.execute(
        sa.text("SELECT id, status, merged_into_id FROM companies")
    ).mappings()
    companies = {
        int(row["id"]): {
            "status": row["status"],
            "merged_into_id": row["merged_into_id"],
        }
        for row in company_rows
    }

    customer_rows = conn.execute(
        sa.text(
            "SELECT DISTINCT company_id FROM stripe_customers "
            "WHERE company_id IS NOT NULL"
        )
    ).mappings()
    repoints: dict[int, int] = {}
    for row in customer_rows:
        company_id = int(row["company_id"])
        root_id = _live_root(company_id, companies)
        if root_id is not None and root_id != company_id:
            repoints[company_id] = root_id

    for from_id, to_id in repoints.items():
        conn.execute(
            sa.text(
                "UPDATE stripe_customers "
                "SET company_id = :to_id "
                "WHERE company_id = :from_id"
            ),
            {"to_id": to_id, "from_id": from_id},
        )


def downgrade() -> None:
    # Data-only forward repair; the original merged-away owner cannot be
    # inferred once multiple Stripe customers have been repointed to a root.
    pass
