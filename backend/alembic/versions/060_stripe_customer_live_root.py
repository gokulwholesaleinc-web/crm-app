"""Backfill StripeCustomer company links through merge chains.

Revision ID: 060_stripe_customer_live_root
Revises: 059_marketing_social
Create Date: 2026-06-10
"""

# ruff: noqa: I001
import logging

import sqlalchemy as sa
from alembic import op

revision = "060_stripe_customer_live_root"
down_revision = "059_marketing_social"
branch_labels = None
depends_on = None

logger = logging.getLogger(__name__)
ACTIVE_SUBSCRIPTION_STATUSES = ("active", "trialing", "past_due")


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


def _customer_recency_key(row) -> tuple[bool, object, int]:
    return (
        row["created_at"] is not None,
        row["created_at"],
        int(row["id"]),
    )


def _company_customer_coalesce_plan(
    customer_rows,
) -> tuple[int | None, list[int], str | None]:
    """Pick the safest company-owned StripeCustomer and loser ids."""
    rows = list(customer_rows)
    if not rows:
        return None, [], None

    live_rows = [
        row
        for row in rows
        if int(row["active_subscription_count"] or 0) > 0
        or int(row["payment_count"] or 0) > 0
    ]
    if len(live_rows) > 1:
        return None, [], "multiple StripeCustomer rows have live billing links"

    active_subscription_rows = [
        row for row in rows if int(row["active_subscription_count"] or 0) > 0
    ]
    if active_subscription_rows:
        keep = max(active_subscription_rows, key=_customer_recency_key)
    else:
        payment_rows = [row for row in rows if int(row["payment_count"] or 0) > 0]
        keep = max(payment_rows or rows, key=_customer_recency_key)

    keep_id = int(keep["id"])
    return keep_id, [int(row["id"]) for row in rows if int(row["id"]) != keep_id], None


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
        "SELECT sc.id, sc.created_at, sc.stripe_customer_id, "
        "(SELECT COUNT(*) FROM subscriptions s "
        "WHERE s.customer_id = sc.id AND s.status IN :active_statuses) "
        "AS active_subscription_count, "
        "(SELECT COUNT(*) FROM payments p WHERE p.customer_id = sc.id) AS payment_count "
        "FROM stripe_customers sc "
        "WHERE sc.company_id IN :company_ids AND sc.contact_id IS NULL"
    ).bindparams(
        sa.bindparam("company_ids", expanding=True),
        sa.bindparam("active_statuses", expanding=True),
    )
    customer_rows = list(
        conn.execute(
            stmt,
            {
                "company_ids": company_ids,
                "active_statuses": ACTIVE_SUBSCRIPTION_STATUSES,
            },
        ).mappings()
    )
    keep_id, loser_ids, skip_reason = _company_customer_coalesce_plan(customer_rows)
    if skip_reason:
        customer_ids = [int(row["id"]) for row in customer_rows]
        logger.warning(
            "Skipping StripeCustomer coalesce for company %s: %s (candidate_ids=%s)",
            target_company_id,
            skip_reason,
            customer_ids,
        )
        _execute_expanding(
            conn,
            "UPDATE stripe_customers SET company_id = :to_id "
            "WHERE id IN :customer_ids",
            {"to_id": target_company_id, "customer_ids": customer_ids},
            "customer_ids",
        )
        return
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
            "UPDATE stripe_customers SET company_id = NULL, contact_id = NULL "
            "WHERE id IN :loser_ids",
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

    company_id_rows = conn.execute(
        sa.text(
            "SELECT DISTINCT company_id FROM stripe_customers "
            "WHERE company_id IS NOT NULL"
        )
    ).mappings()
    root_company_ids: dict[int, set[int]] = {}
    for row in company_id_rows:
        company_id = int(row["company_id"])
        root_id = _live_root(company_id, companies)
        if root_id is not None:
            root_company_ids.setdefault(root_id, set()).update({company_id, root_id})

    for root_id, company_ids in root_company_ids.items():
        _execute_expanding(
            conn,
            "UPDATE stripe_customers "
            "SET company_id = :to_id "
            "WHERE company_id IN :company_ids "
            "AND contact_id IS NOT NULL",
            {"to_id": root_id, "company_ids": sorted(company_ids)},
            "company_ids",
        )
        _coalesce_company_owned_customers(
            conn,
            company_ids=sorted(company_ids),
            target_company_id=root_id,
        )


def downgrade() -> None:
    # Data-only forward repair; the original merged-away owner cannot be
    # inferred once multiple Stripe customers have been repointed to a root.
    pass
