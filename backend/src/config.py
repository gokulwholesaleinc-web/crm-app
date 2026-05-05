import json
import logging
import os

from pydantic_settings import BaseSettings

logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    DATABASE_URL: str = ""

    SECRET_KEY: str  # Required — no default, fails at startup if missing
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    OPENAI_API_KEY: str = ""

    DEBUG: bool = False
    BACKEND_CORS_ORIGINS: str = '["*"]'

    DATABASE_SSL_VERIFY: bool = False

    # Display-only default for the From header in queue history when an
    # email row didn't store its sender address. Outbound mail itself is
    # sent via the user's connected Gmail account (see email/service.py
    # _try_gmail_send) — there is no transactional provider fallback.
    EMAIL_FROM: str = "no-reply@example.com"

    STRIPE_SECRET_KEY: str = ""
    STRIPE_PUBLISHABLE_KEY: str = ""
    STRIPE_WEBHOOK_SECRET: str = ""

    # Public-facing frontend URL, used to build Stripe Checkout
    # success_url/cancel_url and post-accept payment redirects for
    # public proposal/quote pages. No trailing slash.
    FRONTEND_BASE_URL: str = ""

    META_ACCESS_TOKEN: str = ""
    META_APP_ID: str = ""
    META_APP_SECRET: str = ""
    META_WEBHOOK_VERIFY_TOKEN: str = "crm_meta_webhook"

    GOOGLE_CLIENT_ID: str = ""
    GOOGLE_CLIENT_SECRET: str = ""

    # Mailchimp boot-time seed — when set, the startup hook in
    # main.py::_init_database creates a per-tenant MailchimpConnection
    # for any active tenant that doesn't already have one. The UI
    # Connect form remains the source of truth for ad-hoc updates and
    # for tenants whose key differs from the env value.
    MAILCHIMP_API_KEY: str = ""
    MAILCHIMP_DEFAULT_AUDIENCE_ID: str = ""

    SEED_ON_STARTUP: bool = False

    @property
    def cors_origins(self) -> list[str]:
        origins = json.loads(self.BACKEND_CORS_ORIGINS)
        if "*" in origins:
            return ["*"]
        return origins

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
