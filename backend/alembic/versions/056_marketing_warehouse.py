"""Marketing Analytics warehouse — Cluster A+B (landing + dims + facts + ops).

Revision ID: 056_marketing_warehouse
Revises: 055_onboarding_bundles
Create Date: 2026-06-08

Creates the 13 tables of the in-CRM marketing analytics warehouse (PART III
clusters A + B): config dimension ``platform_connections`` (with encrypted token
columns), the ``marketing_campaigns``/``marketing_ad_groups`` dims, the
``marketing_raw_payloads`` landing table (JSONB, the re-derivation hedge), the
``ads_daily_metrics``/``analytics_daily``/``site_health_snapshots`` facts, and
the ops/security tables (``marketing_sync_runs``, ``marketing_credential_audit``,
``budget_periods``, ``marketing_report_schedules``, ``marketing_alerts``,
``fx_rates``).

Correctness-critical DDL:
* The upsert conflict keys (``uq_ads_daily_metrics_grain``,
  ``uq_analytics_daily_grain``, ``uq_site_health_snapshots_grain``,
  ``uq_marketing_raw_payloads_key``) are ``UNIQUE … NULLS NOT DISTINCT`` so an
  account-level row with NULL campaign/adgroup ids still de-dups on re-run (A2).
  ``NULLS NOT DISTINCT`` needs PG15+ (Neon/PG16). The ``postgresql_nulls_not_distinct``
  kwarg is silently ignored on the SQLite test harness, so this migration and
  ``Base.metadata.create_all`` stay byte-identical there
  (``test_marketing_migration.py`` runs this upgrade on SQLite and diffs them).
* Money + conversions are ``Numeric`` (A4); ingest normalizes Google micros ÷1e6.

Additive + safe (new tables only). The revision id is 23 chars (≤32, respects
the ``alembic_version VARCHAR(32)`` cap that bit migration 054). The JSON column
imports the model's ``_MarketingJSON`` TypeDecorator so PG renders JSONB and
SQLite renders JSON — matching ``create_all`` on both dialects.
"""

import sqlalchemy as sa

from alembic import op
from src.marketing.models import _MarketingJSON

revision = "056_marketing_warehouse"
down_revision = "055_onboarding_bundles"
branch_labels = None
depends_on = None


def _timestamp_cols() -> list[sa.Column]:
    """TimestampMixin columns (created_at indexed separately per table)."""
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    ]


def _auditable_fk(table: str) -> list[sa.ForeignKeyConstraint]:
    """AuditableMixin created_by/updated_by FKs to users (SET NULL)."""
    return [
        sa.ForeignKeyConstraint(
            ["created_by_id"], ["users.id"],
            name=f"fk_{table}_created_by_id_users", ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["updated_by_id"], ["users.id"],
            name=f"fk_{table}_updated_by_id_users", ondelete="SET NULL",
        ),
    ]


def upgrade() -> None:
    # ── platform_connections (AuditableMixin) ──────────────────────────────
    op.create_table(
        "platform_connections",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("platform", sa.String(length=32), nullable=False),
        sa.Column("external_account_id", sa.String(length=255), nullable=False),
        sa.Column("manager_account_id", sa.String(length=64), nullable=True),
        sa.Column("display_name", sa.String(length=255), nullable=True),
        sa.Column("credential_mode", sa.String(length=32), nullable=False),
        sa.Column("access_token_ciphertext", sa.LargeBinary(), nullable=True),
        sa.Column("refresh_token_ciphertext", sa.LargeBinary(), nullable=True),
        sa.Column("token_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("token_key_version", sa.SmallInteger(), nullable=True),
        sa.Column("currency", sa.String(length=3), nullable=True),
        sa.Column("reporting_timezone", sa.String(length=64), server_default="UTC", nullable=False),
        sa.Column("conversion_window_days", sa.SmallInteger(), server_default="30", nullable=False),
        sa.Column("status", sa.String(length=32), server_default="pending", nullable=False),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("failure_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("is_enabled", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("created_by_id", sa.Integer(), nullable=True),
        sa.Column("updated_by_id", sa.Integer(), nullable=True),
        *_timestamp_cols(),
        sa.ForeignKeyConstraint(
            ["company_id"], ["companies.id"],
            name="fk_platform_connections_company_id_companies", ondelete="CASCADE",
        ),
        *_auditable_fk("platform_connections"),
        sa.PrimaryKeyConstraint("id", name="pk_platform_connections"),
        sa.UniqueConstraint(
            "company_id", "platform", "external_account_id",
            name="uq_platform_connections_identity",
        ),
        sa.CheckConstraint(
            "platform IN ('google_ads', 'ga4', 'gsc', 'pagespeed', 'meta_ads', "
            "'instagram', 'facebook', 'tiktok', 'linkedin')",
            name="ck_platform_connections_platform",
        ),
        sa.CheckConstraint(
            "credential_mode IN ('agency_oauth', 'client_oauth', 'system_user', "
            "'mcc_link', 'api_key')",
            name="ck_platform_connections_credential_mode",
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'active', 'needs_reauth', 'error', 'disabled')",
            name="ck_platform_connections_status",
        ),
    )
    op.create_index("ix_platform_connections_created_at", "platform_connections", ["created_at"])
    op.create_index(
        "ix_platform_connections_company_platform", "platform_connections", ["company_id", "platform"]
    )

    # ── marketing_campaigns (TimestampMixin) ───────────────────────────────
    op.create_table(
        "marketing_campaigns",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("connection_id", sa.Integer(), nullable=False),
        sa.Column("campaign_id", sa.String(length=128), nullable=False),
        sa.Column("name", sa.String(length=512), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=True),
        sa.Column("raw_status", sa.String(length=64), nullable=True),
        *_timestamp_cols(),
        sa.ForeignKeyConstraint(
            ["connection_id"], ["platform_connections.id"],
            name="fk_marketing_campaigns_connection_id", ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_marketing_campaigns"),
        sa.UniqueConstraint("connection_id", "campaign_id", name="uq_marketing_campaigns_identity"),
    )
    op.create_index("ix_marketing_campaigns_created_at", "marketing_campaigns", ["created_at"])

    # ── marketing_ad_groups (TimestampMixin) ───────────────────────────────
    op.create_table(
        "marketing_ad_groups",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("connection_id", sa.Integer(), nullable=False),
        sa.Column("adgroup_id", sa.String(length=128), nullable=False),
        sa.Column("campaign_id", sa.String(length=128), nullable=True),
        sa.Column("name", sa.String(length=512), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=True),
        *_timestamp_cols(),
        sa.ForeignKeyConstraint(
            ["connection_id"], ["platform_connections.id"],
            name="fk_marketing_ad_groups_connection_id", ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_marketing_ad_groups"),
        sa.UniqueConstraint("connection_id", "adgroup_id", name="uq_marketing_ad_groups_identity"),
    )
    op.create_index("ix_marketing_ad_groups_created_at", "marketing_ad_groups", ["created_at"])

    # ── marketing_raw_payloads (landing, no mixin) ─────────────────────────
    op.create_table(
        "marketing_raw_payloads",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("connection_id", sa.Integer(), nullable=False),
        sa.Column("platform", sa.String(length=32), nullable=False),
        sa.Column("endpoint", sa.String(length=128), nullable=False),
        sa.Column("window_start", sa.Date(), nullable=False),
        sa.Column("window_end", sa.Date(), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("request_fingerprint", sa.String(length=128), nullable=False),
        sa.Column("payload", _MarketingJSON(), nullable=False),
        sa.Column("row_count", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(
            ["connection_id"], ["platform_connections.id"],
            name="fk_marketing_raw_payloads_connection_id", ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_marketing_raw_payloads"),
        sa.UniqueConstraint(
            "connection_id", "endpoint", "window_start", "window_end", "fetched_at",
            name="uq_marketing_raw_payloads_key", postgresql_nulls_not_distinct=True,
        ),
    )
    op.create_index("ix_marketing_raw_payloads_fetched_at", "marketing_raw_payloads", ["fetched_at"])
    op.create_index(
        "ix_marketing_raw_payloads_window", "marketing_raw_payloads",
        ["connection_id", "window_start", "window_end"],
    )

    # ── ads_daily_metrics (fact, TimestampMixin) ───────────────────────────
    op.create_table(
        "ads_daily_metrics",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("connection_id", sa.Integer(), nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("platform", sa.String(length=32), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("entity_level", sa.String(length=16), nullable=False),
        sa.Column("campaign_id", sa.String(length=128), nullable=True),
        sa.Column("adgroup_id", sa.String(length=128), nullable=True),
        sa.Column("spend", sa.Numeric(18, 6), server_default="0", nullable=False),
        sa.Column("impressions", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("clicks", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("conversions", sa.Numeric(18, 6), server_default="0", nullable=False),
        sa.Column("conversion_value", sa.Numeric(18, 6), server_default="0", nullable=False),
        sa.Column("reach", sa.BigInteger(), nullable=True),
        sa.Column("purchases", sa.Numeric(18, 6), nullable=True),
        sa.Column("currency", sa.String(length=3), nullable=True),
        *_timestamp_cols(),
        sa.ForeignKeyConstraint(
            ["connection_id"], ["platform_connections.id"],
            name="fk_ads_daily_metrics_connection_id", ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_ads_daily_metrics"),
        sa.UniqueConstraint(
            "connection_id", "date", "entity_level", "campaign_id", "adgroup_id",
            name="uq_ads_daily_metrics_grain", postgresql_nulls_not_distinct=True,
        ),
        sa.CheckConstraint(
            "entity_level IN ('account', 'campaign', 'adgroup')",
            name="ck_ads_daily_metrics_entity_level",
        ),
    )
    op.create_index("ix_ads_daily_metrics_created_at", "ads_daily_metrics", ["created_at"])
    op.create_index(
        "ix_ads_daily_metrics_company_platform_date", "ads_daily_metrics",
        ["company_id", "platform", "date"],
    )
    op.create_index("ix_ads_daily_metrics_company_date", "ads_daily_metrics", ["company_id", "date"])
    op.create_index("ix_ads_daily_metrics_connection_date", "ads_daily_metrics", ["connection_id", "date"])

    # ── analytics_daily (fact, TimestampMixin) ─────────────────────────────
    op.create_table(
        "analytics_daily",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("connection_id", sa.Integer(), nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(length=8), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("dimension_type", sa.String(length=32), nullable=False),
        sa.Column("dimension_value", sa.String(length=512), server_default="", nullable=False),
        sa.Column("sessions", sa.BigInteger(), nullable=True),
        sa.Column("users", sa.BigInteger(), nullable=True),
        sa.Column("new_users", sa.BigInteger(), nullable=True),
        sa.Column("engaged_sessions", sa.BigInteger(), nullable=True),
        sa.Column("engagement_rate", sa.Numeric(9, 6), nullable=True),
        sa.Column("bounce_rate", sa.Numeric(9, 6), nullable=True),
        sa.Column("conversions", sa.Numeric(18, 6), nullable=True),
        sa.Column("key_events", sa.Numeric(18, 6), nullable=True),
        sa.Column("avg_session_duration", sa.Numeric(12, 4), nullable=True),
        sa.Column("impressions", sa.BigInteger(), nullable=True),
        sa.Column("clicks", sa.BigInteger(), nullable=True),
        sa.Column("ctr", sa.Numeric(9, 6), nullable=True),
        sa.Column("position", sa.Numeric(9, 4), nullable=True),
        sa.Column("is_sampled", sa.Boolean(), server_default=sa.false(), nullable=False),
        *_timestamp_cols(),
        sa.ForeignKeyConstraint(
            ["connection_id"], ["platform_connections.id"],
            name="fk_analytics_daily_connection_id", ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_analytics_daily"),
        sa.UniqueConstraint(
            "connection_id", "date", "source", "dimension_type", "dimension_value",
            name="uq_analytics_daily_grain", postgresql_nulls_not_distinct=True,
        ),
        sa.CheckConstraint("source IN ('ga4', 'gsc')", name="ck_analytics_daily_source"),
        sa.CheckConstraint(
            "dimension_type IN ('total', 'channel', 'page', 'query', 'source_medium')",
            name="ck_analytics_daily_dimension_type",
        ),
    )
    op.create_index("ix_analytics_daily_created_at", "analytics_daily", ["created_at"])
    op.create_index(
        "ix_analytics_daily_company_source_date", "analytics_daily", ["company_id", "source", "date"]
    )

    # ── site_health_snapshots (fact, no mixin) ─────────────────────────────
    op.create_table(
        "site_health_snapshots",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("connection_id", sa.Integer(), nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("captured_date", sa.Date(), nullable=False),
        sa.Column("strategy", sa.String(length=16), nullable=False),
        sa.Column("url", sa.String(length=1024), nullable=False),
        sa.Column("performance_score", sa.Numeric(5, 2), nullable=True),
        sa.Column("seo_score", sa.Numeric(5, 2), nullable=True),
        sa.Column("accessibility_score", sa.Numeric(5, 2), nullable=True),
        sa.Column("best_practices_score", sa.Numeric(5, 2), nullable=True),
        sa.Column("lcp_ms", sa.Integer(), nullable=True),
        sa.Column("cls", sa.Numeric(6, 3), nullable=True),
        sa.Column("inp_ms", sa.Integer(), nullable=True),
        sa.Column("fetched_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["connection_id"], ["platform_connections.id"],
            name="fk_site_health_snapshots_connection_id", ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_site_health_snapshots"),
        sa.UniqueConstraint(
            "connection_id", "captured_date", "strategy", "url",
            name="uq_site_health_snapshots_grain", postgresql_nulls_not_distinct=True,
        ),
        sa.CheckConstraint(
            "strategy IN ('mobile', 'desktop')", name="ck_site_health_snapshots_strategy"
        ),
    )
    op.create_index(
        "ix_site_health_snapshots_company_date", "site_health_snapshots", ["company_id", "captured_date"]
    )

    # ── marketing_sync_runs (ops, no mixin) ────────────────────────────────
    op.create_table(
        "marketing_sync_runs",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("connection_id", sa.Integer(), nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("platform", sa.String(length=32), nullable=False),
        sa.Column("run_type", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("window_start", sa.Date(), nullable=True),
        sa.Column("window_end", sa.Date(), nullable=True),
        sa.Column("rows_upserted", sa.Integer(), server_default="0", nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("error_class", sa.String(length=64), nullable=True),
        sa.ForeignKeyConstraint(
            ["connection_id"], ["platform_connections.id"],
            name="fk_marketing_sync_runs_connection_id", ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_marketing_sync_runs"),
        sa.CheckConstraint(
            "run_type IN ('daily', 'backfill', 'settling', 'manual')",
            name="ck_marketing_sync_runs_run_type",
        ),
        sa.CheckConstraint(
            "status IN ('running', 'success', 'error', 'partial')",
            name="ck_marketing_sync_runs_status",
        ),
    )
    op.create_index("ix_marketing_sync_runs_company_id", "marketing_sync_runs", ["company_id"])
    op.create_index(
        "ix_marketing_sync_runs_connection_started", "marketing_sync_runs",
        ["connection_id", "started_at"],
    )

    # ── marketing_credential_audit (append-only, no mixin) ─────────────────
    op.create_table(
        "marketing_credential_audit",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("connection_id", sa.Integer(), nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("platform", sa.String(length=32), nullable=False),
        sa.Column("actor_type", sa.String(length=16), nullable=False),
        sa.Column("actor_user_id", sa.Integer(), nullable=True),
        sa.Column("action", sa.String(length=32), nullable=False),
        sa.Column("detail", sa.String(length=512), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["connection_id"], ["platform_connections.id"],
            name="fk_marketing_credential_audit_connection_id", ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["actor_user_id"], ["users.id"],
            name="fk_marketing_credential_audit_actor_user_id_users", ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_marketing_credential_audit"),
        sa.CheckConstraint(
            "actor_type IN ('ingest', 'admin', 'refresh', 'reconnect', 'system')",
            name="ck_marketing_credential_audit_actor_type",
        ),
        sa.CheckConstraint(
            "action IN ('access', 'refresh', 'reconnect', 'revoke', 'create', 'rotate')",
            name="ck_marketing_credential_audit_action",
        ),
    )
    op.create_index(
        "ix_marketing_credential_audit_connection_id", "marketing_credential_audit", ["connection_id"]
    )
    op.create_index(
        "ix_marketing_credential_audit_created_at", "marketing_credential_audit", ["created_at"]
    )
    op.create_index(
        "ix_marketing_credential_audit_company_created", "marketing_credential_audit",
        ["company_id", "created_at"],
    )

    # ── budget_periods (TimestampMixin) ────────────────────────────────────
    op.create_table(
        "budget_periods",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("connection_id", sa.Integer(), nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("period_month", sa.Date(), nullable=False),
        sa.Column("amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        *_timestamp_cols(),
        sa.ForeignKeyConstraint(
            ["connection_id"], ["platform_connections.id"],
            name="fk_budget_periods_connection_id", ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_budget_periods"),
        sa.UniqueConstraint("connection_id", "period_month", name="uq_budget_periods_period"),
    )
    op.create_index("ix_budget_periods_company_id", "budget_periods", ["company_id"])
    op.create_index("ix_budget_periods_created_at", "budget_periods", ["created_at"])

    # ── marketing_report_schedules (AuditableMixin, dormant) ───────────────
    op.create_table(
        "marketing_report_schedules",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("cadence", sa.String(length=16), nullable=False),
        sa.Column("recipients", _MarketingJSON(), nullable=False),
        sa.Column("tabs", _MarketingJSON(), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("last_sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by_id", sa.Integer(), nullable=True),
        sa.Column("updated_by_id", sa.Integer(), nullable=True),
        *_timestamp_cols(),
        sa.ForeignKeyConstraint(
            ["company_id"], ["companies.id"],
            name="fk_marketing_report_schedules_company_id_companies", ondelete="CASCADE",
        ),
        *_auditable_fk("marketing_report_schedules"),
        sa.PrimaryKeyConstraint("id", name="pk_marketing_report_schedules"),
        sa.CheckConstraint(
            "cadence IN ('weekly', 'monthly')", name="ck_marketing_report_schedules_cadence"
        ),
    )
    op.create_index(
        "ix_marketing_report_schedules_company_id", "marketing_report_schedules", ["company_id"]
    )
    op.create_index(
        "ix_marketing_report_schedules_created_at", "marketing_report_schedules", ["created_at"]
    )

    # ── marketing_alerts (TimestampMixin, dormant) ─────────────────────────
    op.create_table(
        "marketing_alerts",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("connection_id", sa.Integer(), nullable=True),
        sa.Column("alert_type", sa.String(length=32), nullable=False),
        sa.Column("dedup_key", sa.String(length=255), nullable=False),
        sa.Column("severity", sa.String(length=16), server_default="info", nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("metric_date", sa.Date(), nullable=True),
        sa.Column("last_fired_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("is_resolved", sa.Boolean(), server_default=sa.false(), nullable=False),
        *_timestamp_cols(),
        sa.ForeignKeyConstraint(
            ["company_id"], ["companies.id"],
            name="fk_marketing_alerts_company_id_companies", ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["connection_id"], ["platform_connections.id"],
            name="fk_marketing_alerts_connection_id", ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_marketing_alerts"),
        sa.UniqueConstraint("company_id", "dedup_key", name="uq_marketing_alerts_dedup"),
        sa.CheckConstraint(
            "alert_type IN ('spend_spike', 'spend_drop', 'roas_collapse', "
            "'conversions_zero', 'paused_still_spending', 'stale_sync')",
            name="ck_marketing_alerts_alert_type",
        ),
    )
    op.create_index("ix_marketing_alerts_created_at", "marketing_alerts", ["created_at"])
    op.create_index(
        "ix_marketing_alerts_company_fired", "marketing_alerts", ["company_id", "last_fired_at"]
    )

    # ── fx_rates (TimestampMixin, dormant) ─────────────────────────────────
    op.create_table(
        "fx_rates",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("rate_date", sa.Date(), nullable=False),
        sa.Column("base_currency", sa.String(length=3), nullable=False),
        sa.Column("quote_currency", sa.String(length=3), nullable=False),
        sa.Column("rate", sa.Numeric(18, 8), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=True),
        *_timestamp_cols(),
        sa.PrimaryKeyConstraint("id", name="pk_fx_rates"),
        sa.UniqueConstraint("rate_date", "base_currency", "quote_currency", name="uq_fx_rates_pair"),
    )
    op.create_index("ix_fx_rates_created_at", "fx_rates", ["created_at"])


def downgrade() -> None:
    for table in (
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
    ):
        op.drop_table(table)
