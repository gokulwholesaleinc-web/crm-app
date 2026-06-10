import json
import logging
import os

from pydantic_settings import BaseSettings

logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    DATABASE_URL: str = ""

    SECRET_KEY: str  # Required — no default, fails at startup if missing
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 480  # 8 hours

    DEBUG: bool = False
    # JSON array of allowed origins, e.g. '["https://app.example.com"]'.
    # Must be set explicitly in production — wildcard is rejected at startup when DEBUG=False.
    BACKEND_CORS_ORIGINS: str = '["http://localhost:3000","http://localhost:5173"]'

    DATABASE_SSL_VERIFY: bool = False

    # Display-only default for the From header in queue history when an
    # email row didn't store its sender address. Outbound mail itself is
    # sent via the user's connected Gmail account (see email/service.py
    # _try_gmail_send) — there is no transactional provider fallback.
    EMAIL_FROM: str = "no-reply@example.com"

    STRIPE_SECRET_KEY: str = ""
    STRIPE_PUBLISHABLE_KEY: str = ""
    STRIPE_WEBHOOK_SECRET: str = ""
    STRIPE_API_VERSION: str = "2026-04-22.dahlia"

    # Public-facing frontend origin used throughout the backend for deep-link
    # generation (Stripe Checkout, e-sign, quotes, contracts, notifications,
    # Gmail OAuth). No trailing slash. Required in production.
    FRONTEND_BASE_URL: str = ""

    META_ACCESS_TOKEN: str = ""
    META_APP_ID: str = ""
    META_APP_SECRET: str = ""
    # Required when META_APP_SECRET is set; must be a secret random string
    # configured in the Meta developer dashboard as the webhook verify token.
    META_WEBHOOK_VERIFY_TOKEN: str = ""

    GOOGLE_CLIENT_ID: str = ""
    GOOGLE_CLIENT_SECRET: str = ""

    # Mailchimp boot-time seed — when set, the startup hook in
    # main.py::_init_database creates a per-tenant MailchimpConnection
    # for any active tenant that doesn't already have one. The UI
    # Connect form remains the source of truth for ad-hoc updates and
    # for tenants whose key differs from the env value.
    MAILCHIMP_API_KEY: str = ""
    MAILCHIMP_DEFAULT_AUDIENCE_ID: str = ""

    # ── Marketing Analytics (in-CRM ads/analytics warehouse) ──────────────
    # Dedicated Fernet key for platform OAuth/token encryption at rest. NEVER
    # reuse SECRET_KEY or ONBOARDING_FIELD_KEY (blast-radius isolation, D-cluster).
    # Comma-separated for MultiFernet rotation; fail-closed if a token is handled
    # while unset. Verified at use in marketing/crypto.py.
    MARKETING_TOKEN_KEY: str = ""
    # Separate Google Cloud OAuth client for marketing scopes (adwords +
    # analytics.readonly + webmasters.readonly) — MANDATORY per C3; kept out of
    # the Gmail/Calendar client so its restricted-scope CASA review is untouched.
    GOOGLE_MARKETING_CLIENT_ID: str = ""
    GOOGLE_MARKETING_CLIENT_SECRET: str = ""
    GOOGLE_ADS_DEVELOPER_TOKEN: str = ""
    GOOGLE_ADS_LOGIN_CUSTOMER_ID: str = ""  # Link Creative MCC, digits only
    PAGESPEED_API_KEY: str = ""
    # Dedicated Meta token key for the plaintext→encrypted retrofit (C4).
    META_TOKEN_KEY: str = ""
    # C4 multi-deploy switch. False (expand phase): write BOTH plaintext +
    # ciphertext, read ciphertext-then-plaintext-fallback (safe even before the key
    # is set). Flip True (contract phase) AFTER the backfill: read ciphertext-only +
    # stop writing plaintext, so the legacy column can later be dropped.
    META_TOKEN_ENCRYPTION_STRICT: bool = False

    # Feature flags — every marketing surface ships behind one; defaults keep
    # approval-gated and dormant platforms DARK so the module is safe to deploy
    # before access lands. Flip per-flag once access/decision is confirmed.
    MKTG_ENABLED: bool = False  # master gate for the /reporting feature
    MKTG_META_ENABLED: bool = False  # Phase 2 — Meta Ads (Business Verification gated)
    MKTG_SOCIAL_ENABLED: bool = False  # Phase 4 — IG/FB/TikTok/LinkedIn (App Review gated)
    MKTG_SCHEDULED_DELIVERY: bool = False  # E2/Q12 — scheduled emailed PDF (B4 tables dormant)
    MKTG_ALERTS_ENABLED: bool = False  # B4 anomaly alerts (dormant until Phase 5)
    MKTG_MULTI_CURRENCY: bool = False  # A9/Q11 — default: withhold blended KPIs for multi-currency clients
    MKTG_PORTAL_ENABLED: bool = False  # client read-only portal (MOOT/admin-only v1)

    SEED_ON_STARTUP: bool = False

    @property
    def cors_origins(self) -> list[str]:
        return json.loads(self.BACKEND_CORS_ORIGINS)

    @property
    def db_url(self) -> str:
        """Get database URL with asyncpg driver."""
        if self.DATABASE_URL:
            url = self.DATABASE_URL
            if url.startswith("postgresql://") and "+asyncpg" not in url:
                url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
            if "?sslmode=" in url:
                url = url.split("?sslmode=")[0]
            return url
        host = os.getenv("PGHOST", "localhost")
        port = os.getenv("PGPORT", "5432")
        user = os.getenv("PGUSER", "postgres")
        password = os.getenv("PGPASSWORD", "")
        database = os.getenv("PGDATABASE", "crm_db")
        return f"postgresql+asyncpg://{user}:{password}@{host}:{port}/{database}"

    class Config:
        env_file = ".env"
        case_sensitive = True
        extra = "ignore"


settings = Settings()  # type: ignore[call-arg]  # SECRET_KEY sourced from env; startup fails if unset
