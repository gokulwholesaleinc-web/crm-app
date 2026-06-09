"""In-CRM Marketing Analytics — ads/analytics warehouse + reporting.

Replaces the third-party vendor dashboard (Google-Sheet-backed, shared-password)
with a per-client Postgres warehouse, idempotent ingestion, ratio-of-sums
aggregation, and a branded reporting surface — reusing the CRM's existing OAuth,
scheduler, Fernet encryption, TTL cache, and WeasyPrint PDF primitives.

See MARKETING_ANALYTICS_DASHBOARD_PLAN.md PART III (locked decisions). Every
surface is feature-flagged (config.MKTG_*); approval-gated platforms ship dark.
"""
