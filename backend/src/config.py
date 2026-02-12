from pydantic_settings import BaseSettings
from typing import List
import json
import os


class Settings(BaseSettings):
    # Database - construct from PG env vars if DATABASE_URL not set
    DATABASE_URL: str = ""

    # JWT Authentication
    SECRET_KEY: str = "dev-secret-key-change-in-production"  # Default for development
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    # OpenAI
    OPENAI_API_KEY: str = ""

    # Application
    DEBUG: bool = False
    BACKEND_CORS_ORIGINS: str = '["*"]'

    # Resend Email
    RESEND_API_KEY: str = ""
    EMAIL_FROM: str = "onboarding@resend.dev"

    # Stripe
    STRIPE_SECRET_KEY: str = ""
    STRIPE_PUBLISHABLE_KEY: str = ""
    STRIPE_WEBHOOK_SECRET: str = ""

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
