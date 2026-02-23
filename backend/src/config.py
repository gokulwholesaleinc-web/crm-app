import logging
from typing import List
import json
import os

from pydantic_settings import BaseSettings
from pydantic import model_validator

logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    # Database - construct from PG env vars if DATABASE_URL not set
    DATABASE_URL: str = ""

    # JWT Authentication
    SECRET_KEY: str = "dev-secret-key-DO-NOT-USE-IN-PRODUCTION"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    # OpenAI
    OPENAI_API_KEY: str = ""

    # Application
    DEBUG: bool = False
    BACKEND_CORS_ORIGINS: str = '["http://localhost:3000"]'

    # Database SSL verification (set to "false" to disable SSL cert verification)
    DATABASE_SSL_VERIFY: bool = True

    @model_validator(mode="after")
    def _validate_required_settings(self):
        if not self.DEBUG and self.SECRET_KEY == "dev-secret-key-DO-NOT-USE-IN-PRODUCTION":
            raise ValueError(
                "SECRET_KEY must be set via environment variable in production. "
                "Do not use the default dev key."
            )
        if not self.DEBUG:
            if not self.DATABASE_URL and not os.getenv("PGHOST"):
                raise ValueError(
                    "DATABASE_URL (or PGHOST/PGPORT/PGUSER/PGPASSWORD/PGDATABASE) "
                    "must be set in production."
                )
            if not self.OPENAI_API_KEY:
                logger.warning(
                    "OPENAI_API_KEY is not set; AI features will be disabled."
                )
        return self

    # Resend Email
    RESEND_API_KEY: str = ""
    EMAIL_FROM: str = "onboarding@resend.dev"

    # Stripe
    STRIPE_SECRET_KEY: str = ""
    STRIPE_PUBLISHABLE_KEY: str = ""
    STRIPE_WEBHOOK_SECRET: str = ""

    # Database SSL
    DATABASE_SSL_VERIFY: bool = False

    # Seed data (set to true in .env for initial setup, false for production)
    SEED_ON_STARTUP: bool = False

    @property
    def cors_origins(self) -> List[str]:
        origins = json.loads(self.BACKEND_CORS_ORIGINS)
        if "*" in origins:
            return ["*"]
        return origins

    @property
    def db_url(self) -> str:
        """Get database URL with asyncpg driver."""
        if self.DATABASE_URL:
            url = self.DATABASE_URL
            # Convert postgresql:// to postgresql+asyncpg://
            if url.startswith("postgresql://") and "+asyncpg" not in url:
                url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
            # Remove sslmode parameter if present (not supported by asyncpg)
            if "?sslmode=" in url:
                url = url.split("?sslmode=")[0]
            return url
        # Fallback to constructing from individual PG vars
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


settings = Settings()
