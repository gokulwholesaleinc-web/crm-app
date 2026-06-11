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


def _company_customer_coalesce_plan(customer_rows) -> tuple[int | None, list[int]]:
    """Pick the most-recent company-owned StripeCustomer and loser ids."""
    rows = list(customer_rows)
    if not rows:
        return None, []
    keep = max(
        rows,
        key=lambda row: (
            row["created_at"] is not None,
            row["created_at"],
            int(row["id"]),
        ),
    )
    keep_id = int(keep["id"])
    return keep_id, [int(row["id"]) for row in rows if int(row["id"]) != keep_id]


def _execute_expanding(conn, sql: str, params: dict[str, object], *names: str) -> None:
    stmt = sa.text(sql).bindparams(
        *(sa.bindparam(name, expanding=True) for name in names)
    )
    conn.execute(stmt, params)


def _coalesce_company_owned_customers(
    conn,
    *,
    company_ids: list[int],
    target_company_id: int,
) -> None:
    if not company_ids:
        return

    stmt = sa.text(
        "SELECT id, created_at FROM stripe_customers "
        "WHERE company_id IN :company_ids AND contact_id IS NULL"
    ).bindparams(sa.bindparam("company_ids", expanding=True))
    customer_rows = list(conn.execute(stmt, {"company_ids": company_ids}).mappings())
    keep_id, loser_ids = _company_customer_coalesce_plan(customer_rows)
    if keep_id is None:
        return

    if loser_ids:
        _execute_expanding(
            conn,
            "UPDATE payments SET customer_id = :keep_id "
            "WHERE customer_id IN :loser_ids",
            {"keep_id": keep_id, "loser_ids": loser_ids},
            "loser_ids",
        )
        _execute_expanding(
            conn,
            "UPDATE subscriptions SET customer_id = :keep_id "
            "WHERE customer_id IN :loser_ids",
            {"keep_id": keep_id, "loser_ids": loser_ids},
            "loser_ids",
        )
        _execute_expanding(
            conn,
            "DELETE FROM stripe_customers WHERE id IN :loser_ids",
            {"loser_ids": loser_ids},
            "loser_ids",
        )

    conn.execute(
        sa.text("UPDATE stripe_customers SET company_id = :to_id WHERE id = :keep_id"),
        {"to_id": target_company_id, "keep_id": keep_id},
    )


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
                "WHERE company_id = :from_id "
                "AND contact_id IS NOT NULL"
            ),
            {"to_id": to_id, "from_id": from_id},
        )
        _coalesce_company_owned_customers(
            conn,
            company_ids=[from_id, to_id],
            target_company_id=to_id,
        )


def downgrade() -> None:
    # Data-only forward repair; the original merged-away owner cannot be
    # inferred once multiple Stripe customers have been repointed to a root.
    pass
