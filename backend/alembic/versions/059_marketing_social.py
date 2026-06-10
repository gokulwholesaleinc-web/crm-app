"""Marketing organic-social fact table (Phase 4) — social_daily_metrics.

Adds the generic long-format daily-metric fact for organic social: one row per
``(connection, date, platform, metric_key)`` so Instagram + Facebook (wired now)
and TikTok + LinkedIn (enum-valid, unwired — App-Review-gated) share ONE table
without a per-platform schema change. Additive + safe; the whole feature ships
DARK behind ``MKTG_SOCIAL_ENABLED``.

Mirrors the 056 fact-table conventions exactly (pinned constraint/index names,
``postgresql_nulls_not_distinct`` on the grain, TimestampMixin columns + the
``created_at`` index) so create_all and this migration stay byte-identical
(test_marketing_migration.py parity).
"""

import sqlalchemy as sa
from alembic import op

revision = "059_marketing_social"
down_revision = "058_meta_token_encryption"
branch_labels = None
depends_on = None

_SOCIAL_PLATFORMS_SQL = "platform IN ('instagram', 'facebook', 'tiktok', 'linkedin')"


def upgrade() -> None:
    op.create_table(
        "social_daily_metrics",
        sa.Column("id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), nullable=False),
        sa.Column("connection_id", sa.Integer(), nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("platform", sa.String(length=32), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("metric_key", sa.String(length=64), nullable=False),
        sa.Column("value", sa.Numeric(20, 4), server_default="0", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["connection_id"], ["platform_connections.id"],
            name="fk_social_daily_metrics_connection_id", ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_social_daily_metrics"),
        sa.UniqueConstraint(
            "connection_id", "date", "platform", "metric_key",
            name="uq_social_daily_metrics_grain", postgresql_nulls_not_distinct=True,
        ),
        sa.CheckConstraint(_SOCIAL_PLATFORMS_SQL, name="ck_social_daily_metrics_platform"),
    )
    op.create_index("ix_social_daily_metrics_created_at", "social_daily_metrics", ["created_at"])
    op.create_index(
        "ix_social_daily_metrics_company_platform_date",
        "social_daily_metrics", ["company_id", "platform", "date"],
    )


def downgrade() -> None:
    op.drop_index("ix_social_daily_metrics_company_platform_date", table_name="social_daily_metrics")
    op.drop_index("ix_social_daily_metrics_created_at", table_name="social_daily_metrics")
    op.drop_table("social_daily_metrics")
