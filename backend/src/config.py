import logging
from typing import List
import json
import os

from pydantic_settings import BaseSettings

logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    DATABASE_URL: str = ""

    SECRET_KEY: str = "dev-secret-key-change-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    OPENAI_API_KEY: str = ""

    DEBUG: bool = False
    BACKEND_CORS_ORIGINS: str = '["*"]'

    DATABASE_SSL_VERIFY: bool = False

    RESEND_API_KEY: str = ""
    EMAIL_FROM: str = "onboarding@resend.dev"

    STRIPE_SECRET_KEY: str = ""
    STRIPE_PUBLISHABLE_KEY: str = ""
    STRIPE_WEBHOOK_SECRET: str = ""

    META_ACCESS_TOKEN: str = ""

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


settings = Settings()
