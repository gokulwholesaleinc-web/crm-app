"""Marketing Analytics warehouse — landing + dimension + fact + ops tables.

Two-layer design (PART III cluster A1): a ``marketing_raw_payloads`` landing
table (one JSONB row per API response, prunable, the re-derivation hedge) feeds
narrow derived fact tables that carry IDs + measures only (NO JSONB). Star-lite:
``platform_connections`` config dimension + ``marketing_campaigns`` /
``marketing_ad_groups`` dims + daily facts keyed on a natural composite grain.

Correctness invariants baked into the schema:
* ``entity_level`` on ``ads_daily_metrics`` makes the grain explicit (A2); every
  aggregation filters to exactly one level so mixed-grain SUMs can't double-count.
* Upsert conflict keys use ``NULLS NOT DISTINCT`` (PG15+; Neon/PG16) so an
  account-level row with NULL campaign/adgroup ids still de-dups on re-run (A2).
  The kwarg is silently ignored on the SQLite test harness, so ``create_all`` and
  migration 056 stay byte-identical there (the migration-parity test relies on it).
* Money + conversions are ``Numeric`` (A4) — never float/int. Google Ads micros
  are divided by 1e6 in the ingest mapper *before* upsert (NN-8).

Every constraint/index name is pinned to match what ``Base.metadata.create_all``
emits, so migration 056 produces a byte-identical schema (see
``test_marketing_migration.py``). FK/unique/index names use the project naming
convention (``src/database.py``); CHECK constraints pass the short token and let
the convention prefix ``ck_<table>_``.
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    false,
    func,
    true,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import TypeDecorator

from src.core.mixins.auditable import AuditableMixin, TimestampMixin
from src.database import Base

# ── Enumerations (kept as Python tuples so CHECK + app validation share one source) ──
PLATFORMS = (
    "google_ads",
    "ga4",
    "gsc",
    "pagespeed",
    "meta_ads",
    "instagram",
    "facebook",
    "tiktok",
    "linkedin",
)
CREDENTIAL_MODES = ("agency_oauth", "client_oauth", "system_user", "mcc_link", "api_key")
CONNECTION_STATUSES = ("pending", "active", "needs_reauth", "error", "disabled")
ENTITY_LEVELS = ("account", "campaign", "adgroup")
ANALYTICS_SOURCES = ("ga4", "gsc")
DIMENSION_TYPES = ("total", "channel", "page", "query", "source_medium")
PAGESPEED_STRATEGIES = ("mobile", "desktop")
SYNC_RUN_TYPES = ("daily", "backfill", "settling", "manual")
SYNC_STATUSES = ("running", "success", "error", "partial")
AUDIT_ACTOR_TYPES = ("ingest", "admin", "refresh", "reconnect", "system")
AUDIT_ACTIONS = ("access", "refresh", "reconnect", "revoke", "create", "rotate")
ALERT_TYPES = (
    "spend_spike",
    "spend_drop",
    "roas_collapse",
    "conversions_zero",
    "paused_still_spending",
    "stale_sync",
)


def _in(column: str, values: tuple[str, ...]) -> str:
    """Render a portable ``col IN ('a','b',...)`` CHECK expression."""
    quoted = ", ".join(f"'{v}'" for v in values)
    return f"{column} IN ({quoted})"


class _MarketingJSON(TypeDecorator):
    """JSONB on Postgres, JSON on SQLite (test DB).

    Module-local clone of ``onboarding/models.py:_FieldDefinitions`` so the
    marketing module stays self-contained (no cross-feature import). Used only on
    the landing/config layer — fact tables carry no JSON.
    """

    impl = JSON
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(JSONB())
        return dialect.type_descriptor(JSON())


# ════════════════════════════════════════════════════════════════════════════
# Config / dimension layer
# ════════════════════════════════════════════════════════════════════════════
class PlatformConnection(Base, AuditableMixin):
    """Per-(client × platform × account) config + encrypted creds + health.

    Replaces both the vendor's per-client-config gap and the leaked-token problem.
    ``external_account_id`` is canonical-normalized on write (A10) so the UNIQUE
    can't admit duplicate connections (``act_123`` vs ``123``).
    """

    __tablename__ = "platform_connections"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("companies.id", ondelete="CASCADE", name="fk_platform_connections_company_id_companies"),
        nullable=False,
    )
    platform: Mapped[str] = mapped_column(String(32), nullable=False)
    external_account_id: Mapped[str] = mapped_column(String(255), nullable=False)
    manager_account_id: Mapped[str | None] = mapped_column(String(64))
    display_name: Mapped[str | None] = mapped_column(String(255))
    credential_mode: Mapped[str] = mapped_column(String(32), nullable=False)

    access_token_ciphertext: Mapped[bytes | None] = mapped_column(LargeBinary)
    refresh_token_ciphertext: Mapped[bytes | None] = mapped_column(LargeBinary)
    token_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    token_key_version: Mapped[int | None] = mapped_column(SmallInteger)

    currency: Mapped[str | None] = mapped_column(String(3))
    reporting_timezone: Mapped[str] = mapped_column(
        String(64), nullable=False, server_default="UTC"
    )
    conversion_window_days: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, server_default="30"
    )

    status: Mapped[str] = mapped_column(String(32), nullable=False, server_default="pending")
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
    failure_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=true())

    __table_args__ = (
        UniqueConstraint(
            "company_id", "platform", "external_account_id",
            name="uq_platform_connections_identity",
        ),
        CheckConstraint(_in("platform", PLATFORMS), name="platform"),
        CheckConstraint(_in("credential_mode", CREDENTIAL_MODES), name="credential_mode"),
        CheckConstraint(_in("status", CONNECTION_STATUSES), name="status"),
        Index("ix_platform_connections_company_platform", "company_id", "platform"),
    )


class MarketingCampaign(Base, TimestampMixin):
    """Campaign dimension (A3): name + current status; facts carry IDs only.

    "Active Campaigns" reads ``status`` here; REMOVED campaigns keep their facts.
    """

    __tablename__ = "marketing_campaigns"

    id: Mapped[int] = mapped_column(primary_key=True)
    connection_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("platform_connections.id", ondelete="CASCADE", name="fk_marketing_campaigns_connection_id"),
        nullable=False,
    )
    campaign_id: Mapped[str] = mapped_column(String(128), nullable=False)
    name: Mapped[str | None] = mapped_column(String(512))
    status: Mapped[str | None] = mapped_column(String(32))
    raw_status: Mapped[str | None] = mapped_column(String(64))

    __table_args__ = (
        UniqueConstraint("connection_id", "campaign_id", name="uq_marketing_campaigns_identity"),
    )


class MarketingAdGroup(Base, TimestampMixin):
    """Ad-group dimension (A3)."""

    __tablename__ = "marketing_ad_groups"

    id: Mapped[int] = mapped_column(primary_key=True)
    connection_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("platform_connections.id", ondelete="CASCADE", name="fk_marketing_ad_groups_connection_id"),
        nullable=False,
    )
    adgroup_id: Mapped[str] = mapped_column(String(128), nullable=False)
    campaign_id: Mapped[str | None] = mapped_column(String(128))
    name: Mapped[str | None] = mapped_column(String(512))
    status: Mapped[str | None] = mapped_column(String(32))

    __table_args__ = (
        UniqueConstraint("connection_id", "adgroup_id", name="uq_marketing_ad_groups_identity"),
    )


# ════════════════════════════════════════════════════════════════════════════
# Landing layer (A1) — re-derivation hedge, pruned nightly
# ════════════════════════════════════════════════════════════════════════════
class MarketingRawPayload(Base):
    """One row per API response (JSONB). Facts are re-derivable from these."""

    __tablename__ = "marketing_raw_payloads"

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer(), "sqlite"), primary_key=True
    )
    connection_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("platform_connections.id", ondelete="CASCADE", name="fk_marketing_raw_payloads_connection_id"),
        nullable=False,
    )
    platform: Mapped[str] = mapped_column(String(32), nullable=False)
    endpoint: Mapped[str] = mapped_column(String(128), nullable=False)
    window_start: Mapped[date] = mapped_column(Date, nullable=False)
    window_end: Mapped[date] = mapped_column(Date, nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), index=True
    )
    request_fingerprint: Mapped[str] = mapped_column(String(128), nullable=False)
    payload: Mapped[dict] = mapped_column(_MarketingJSON, nullable=False)
    row_count: Mapped[int | None] = mapped_column(Integer)

    __table_args__ = (
        UniqueConstraint(
            "connection_id", "endpoint", "window_start", "window_end", "fetched_at",
            name="uq_marketing_raw_payloads_key",
            postgresql_nulls_not_distinct=True,
        ),
        Index("ix_marketing_raw_payloads_window", "connection_id", "window_start", "window_end"),
    )


# ════════════════════════════════════════════════════════════════════════════
# Fact layer (no JSONB)
# ════════════════════════════════════════════════════════════════════════════
class AdsDailyMetric(Base, TimestampMixin):
    """Unified Meta + Google Ads daily fact at an explicit ``entity_level`` grain.

    Conflict key ``(connection_id, date, entity_level, campaign_id, adgroup_id)``
    is ``NULLS NOT DISTINCT`` so account-level rows (NULL campaign/adgroup) de-dup
    on re-run (A2). ``spend``/``conversions``/``conversion_value`` are ``Numeric``
    (A4); Google micros are normalized ÷1e6 in the mapper before upsert (NN-8).
    """

    __tablename__ = "ads_daily_metrics"

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer(), "sqlite"), primary_key=True
    )
    connection_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("platform_connections.id", ondelete="CASCADE", name="fk_ads_daily_metrics_connection_id"),
        nullable=False,
    )
    company_id: Mapped[int] = mapped_column(Integer, nullable=False)
    platform: Mapped[str] = mapped_column(String(32), nullable=False)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    entity_level: Mapped[str] = mapped_column(String(16), nullable=False)
    campaign_id: Mapped[str | None] = mapped_column(String(128))
    adgroup_id: Mapped[str | None] = mapped_column(String(128))

    spend: Mapped[float] = mapped_column(Numeric(18, 6), nullable=False, server_default="0")
    impressions: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")
    clicks: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")
    conversions: Mapped[float] = mapped_column(Numeric(18, 6), nullable=False, server_default="0")
    conversion_value: Mapped[float] = mapped_column(Numeric(18, 6), nullable=False, server_default="0")
    reach: Mapped[int | None] = mapped_column(BigInteger)
    purchases: Mapped[float | None] = mapped_column(Numeric(18, 6))
    currency: Mapped[str | None] = mapped_column(String(3))

    __table_args__ = (
        UniqueConstraint(
            "connection_id", "date", "entity_level", "campaign_id", "adgroup_id",
            name="uq_ads_daily_metrics_grain",
            postgresql_nulls_not_distinct=True,
        ),
        CheckConstraint(_in("entity_level", ENTITY_LEVELS), name="entity_level"),
        Index("ix_ads_daily_metrics_company_platform_date", "company_id", "platform", "date"),
        Index("ix_ads_daily_metrics_company_date", "company_id", "date"),
        Index("ix_ads_daily_metrics_connection_date", "connection_id", "date"),
    )


class AnalyticsDaily(Base, TimestampMixin):
    """GA4 + GSC daily fact, dimension-keyed. Totals come ONLY from
    ``dimension_type='total'`` queries — never summed dimension rows (A11)."""

    __tablename__ = "analytics_daily"

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer(), "sqlite"), primary_key=True
    )
    connection_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("platform_connections.id", ondelete="CASCADE", name="fk_analytics_daily_connection_id"),
        nullable=False,
    )
    company_id: Mapped[int] = mapped_column(Integer, nullable=False)
    source: Mapped[str] = mapped_column(String(8), nullable=False)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    dimension_type: Mapped[str] = mapped_column(String(32), nullable=False)
    dimension_value: Mapped[str] = mapped_column(String(512), nullable=False, server_default="")

    # GA4 measures
    sessions: Mapped[int | None] = mapped_column(BigInteger)
    users: Mapped[int | None] = mapped_column(BigInteger)
    new_users: Mapped[int | None] = mapped_column(BigInteger)
    engaged_sessions: Mapped[int | None] = mapped_column(BigInteger)
    engagement_rate: Mapped[float | None] = mapped_column(Numeric(9, 6))
    bounce_rate: Mapped[float | None] = mapped_column(Numeric(9, 6))
    conversions: Mapped[float | None] = mapped_column(Numeric(18, 6))
    key_events: Mapped[float | None] = mapped_column(Numeric(18, 6))
    avg_session_duration: Mapped[float | None] = mapped_column(Numeric(12, 4))
    # GSC measures
    impressions: Mapped[int | None] = mapped_column(BigInteger)
    clicks: Mapped[int | None] = mapped_column(BigInteger)
    ctr: Mapped[float | None] = mapped_column(Numeric(9, 6))
    position: Mapped[float | None] = mapped_column(Numeric(9, 4))

    is_sampled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=false())
    # H3: golden = no "(other)" overflow + finalized. False surfaces a tie-out caveat.
    is_data_golden: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=true())

    __table_args__ = (
        UniqueConstraint(
            "connection_id", "date", "source", "dimension_type", "dimension_value",
            name="uq_analytics_daily_grain",
            postgresql_nulls_not_distinct=True,
        ),
        CheckConstraint(_in("source", ANALYTICS_SOURCES), name="source"),
        CheckConstraint(_in("dimension_type", DIMENSION_TYPES), name="dimension_type"),
        Index("ix_analytics_daily_company_source_date", "company_id", "source", "date"),
        # LOW-IDX: every channel/page/query read filters on dimension_type — this
        # composite matches the (=company_id, =source, =dimension_type, date BETWEEN)
        # access pattern so those reads don't filter-discard other dimension_types.
        Index(
            "ix_analytics_daily_company_source_dim_date",
            "company_id", "source", "dimension_type", "date",
        ),
    )


class SiteHealthSnapshot(Base):
    """PageSpeed/Lighthouse snapshot (not daily-dense)."""

    __tablename__ = "site_health_snapshots"

    id: Mapped[int] = mapped_column(primary_key=True)
    connection_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("platform_connections.id", ondelete="CASCADE", name="fk_site_health_snapshots_connection_id"),
        nullable=False,
    )
    company_id: Mapped[int] = mapped_column(Integer, nullable=False)
    captured_date: Mapped[date] = mapped_column(Date, nullable=False)
    strategy: Mapped[str] = mapped_column(String(16), nullable=False)
    url: Mapped[str] = mapped_column(String(1024), nullable=False)
    performance_score: Mapped[float | None] = mapped_column(Numeric(5, 2))
    seo_score: Mapped[float | None] = mapped_column(Numeric(5, 2))
    accessibility_score: Mapped[float | None] = mapped_column(Numeric(5, 2))
    best_practices_score: Mapped[float | None] = mapped_column(Numeric(5, 2))
    lcp_ms: Mapped[int | None] = mapped_column(Integer)
    cls: Mapped[float | None] = mapped_column(Numeric(6, 3))
    inp_ms: Mapped[int | None] = mapped_column(Integer)
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        UniqueConstraint(
            "connection_id", "captured_date", "strategy", "url",
            name="uq_site_health_snapshots_grain",
            postgresql_nulls_not_distinct=True,
        ),
        CheckConstraint(_in("strategy", PAGESPEED_STRATEGIES), name="strategy"),
        Index("ix_site_health_snapshots_company_date", "company_id", "captured_date"),
    )


# ════════════════════════════════════════════════════════════════════════════
# Ops / security / scheduling layer (Cluster B)
# ════════════════════════════════════════════════════════════════════════════
class MarketingSyncRun(Base):
    """One row per connection per ingestion run — powers truthful freshness."""

    __tablename__ = "marketing_sync_runs"

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer(), "sqlite"), primary_key=True
    )
    connection_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("platform_connections.id", ondelete="CASCADE", name="fk_marketing_sync_runs_connection_id"),
        nullable=False,
    )
    company_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    platform: Mapped[str] = mapped_column(String(32), nullable=False)
    run_type: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    window_start: Mapped[date | None] = mapped_column(Date)
    window_end: Mapped[date | None] = mapped_column(Date)
    # Rows TOUCHED by the upsert (inserts + ON CONFLICT updates), not net-new — a
    # steady-state re-sync restates the whole window, so this equals the window size,
    # not the number of changed rows. It is an activity/diagnostic counter only.
    rows_upserted: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error: Mapped[str | None] = mapped_column(Text)
    error_class: Mapped[str | None] = mapped_column(String(64))

    __table_args__ = (
        CheckConstraint(_in("run_type", SYNC_RUN_TYPES), name="run_type"),
        CheckConstraint(_in("status", SYNC_STATUSES), name="status"),
        Index("ix_marketing_sync_runs_connection_started", "connection_id", "started_at"),
    )


class MarketingCredentialAudit(Base):
    """Append-only access log per credential — NEVER the token value (B1)."""

    __tablename__ = "marketing_credential_audit"

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer(), "sqlite"), primary_key=True
    )
    connection_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("platform_connections.id", ondelete="CASCADE", name="fk_marketing_credential_audit_connection_id"),
        nullable=False,
        index=True,
    )
    company_id: Mapped[int] = mapped_column(Integer, nullable=False)
    platform: Mapped[str] = mapped_column(String(32), nullable=False)
    actor_type: Mapped[str] = mapped_column(String(16), nullable=False)
    actor_user_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL", name="fk_marketing_credential_audit_actor_user_id_users"),
    )
    action: Mapped[str] = mapped_column(String(32), nullable=False)
    detail: Mapped[str | None] = mapped_column(String(512))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), index=True
    )

    __table_args__ = (
        CheckConstraint(_in("actor_type", AUDIT_ACTOR_TYPES), name="actor_type"),
        CheckConstraint(_in("action", AUDIT_ACTIONS), name="action"),
        Index("ix_marketing_credential_audit_company_created", "company_id", "created_at"),
    )


class BudgetPeriod(Base, TimestampMixin):
    """Per-month budget (B3) — a scalar can't do past-month/YoY pacing."""

    __tablename__ = "budget_periods"

    id: Mapped[int] = mapped_column(primary_key=True)
    connection_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("platform_connections.id", ondelete="CASCADE", name="fk_budget_periods_connection_id"),
        nullable=False,
    )
    company_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    period_month: Mapped[date] = mapped_column(Date, nullable=False)
    amount: Mapped[float] = mapped_column(Numeric(18, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)

    __table_args__ = (
        UniqueConstraint("connection_id", "period_month", name="uq_budget_periods_period"),
    )


class MarketingReportSchedule(Base, AuditableMixin):
    """Scheduled emailed-PDF delivery (B4) — DORMANT until ``MKTG_SCHEDULED_DELIVERY``."""

    __tablename__ = "marketing_report_schedules"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("companies.id", ondelete="CASCADE", name="fk_marketing_report_schedules_company_id_companies"),
        nullable=False,
        index=True,
    )
    cadence: Mapped[str] = mapped_column(String(16), nullable=False)
    recipients: Mapped[list] = mapped_column(_MarketingJSON, nullable=False)
    tabs: Mapped[list | None] = mapped_column(_MarketingJSON)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=false())
    last_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    next_due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint("cadence IN ('weekly', 'monthly')", name="cadence"),
    )


class MarketingAlert(Base, TimestampMixin):
    """Anomaly alert (B4) — DORMANT until ``MKTG_ALERTS_ENABLED``. Dedup +
    suppression-on-failed-ingest live in the alerts engine, not the schema."""

    __tablename__ = "marketing_alerts"

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer(), "sqlite"), primary_key=True
    )
    company_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("companies.id", ondelete="CASCADE", name="fk_marketing_alerts_company_id_companies"),
        nullable=False,
    )
    connection_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("platform_connections.id", ondelete="SET NULL", name="fk_marketing_alerts_connection_id"),
    )
    alert_type: Mapped[str] = mapped_column(String(32), nullable=False)
    dedup_key: Mapped[str] = mapped_column(String(255), nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False, server_default="info")
    message: Mapped[str] = mapped_column(Text, nullable=False)
    metric_date: Mapped[date | None] = mapped_column(Date)
    last_fired_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    is_resolved: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=false())

    __table_args__ = (
        UniqueConstraint("company_id", "dedup_key", name="uq_marketing_alerts_dedup"),
        CheckConstraint(_in("alert_type", ALERT_TYPES), name="alert_type"),
        Index("ix_marketing_alerts_company_fired", "company_id", "last_fired_at"),
    )


class FxRate(Base, TimestampMixin):
    """Per-date FX (A9) — DORMANT unless ``MKTG_MULTI_CURRENCY``. Conversion is
    applied at the reporting layer at the spend date; raw amounts never mixed."""

    __tablename__ = "fx_rates"

    id: Mapped[int] = mapped_column(primary_key=True)
    rate_date: Mapped[date] = mapped_column(Date, nullable=False)
    base_currency: Mapped[str] = mapped_column(String(3), nullable=False)
    quote_currency: Mapped[str] = mapped_column(String(3), nullable=False)
    rate: Mapped[float] = mapped_column(Numeric(18, 8), nullable=False)
    source: Mapped[str | None] = mapped_column(String(32))

    __table_args__ = (
        UniqueConstraint("rate_date", "base_currency", "quote_currency", name="uq_fx_rates_pair"),
    )
