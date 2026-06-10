"""Marketing Phase 2 — GA4 truthfulness column + analytics read index.

Revision ID: 057_marketing_phase2_ga4
Revises: 056_marketing_warehouse
Create Date: 2026-06-09

Additive + safe (no data migration):
* ``analytics_daily.is_data_golden`` (Boolean NOT NULL, server_default true) — H3.
  False when a GA4 report had a high-cardinality "(other)" overflow
  (``metadata.dataLossFromOtherRow``) or was not yet finalized
  (``metadata.dataGolden=False``), so the read layer can disclose a possible
  tie-out gap (A11). Existing rows default to golden=true.
* ``ix_analytics_daily_company_source_dim_date`` (company_id, source,
  dimension_type, date) — LOW-IDX. Every channel/page/query read filters on
  ``dimension_type``; the prior index omitted it, forcing a post-index residual
  filter that discards other dimension_types.

Kept byte-identical with the model so ``test_marketing_migration`` (which now runs
056 → 057 and diffs against ``create_all``) stays green on SQLite.
"""

import sqlalchemy as sa
from alembic import op

revision = "057_marketing_phase2_ga4"
down_revision = "056_marketing_warehouse"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "analytics_daily",
        sa.Column(
            "is_data_golden",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
    )
    op.create_index(
        "ix_analytics_daily_company_source_dim_date",
        "analytics_daily",
        ["company_id", "source", "dimension_type", "date"],
    )


def downgrade() -> None:
    op.drop_index("ix_analytics_daily_company_source_dim_date", table_name="analytics_daily")
    op.drop_column("analytics_daily", "is_data_golden")
