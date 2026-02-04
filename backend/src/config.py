from pydantic_settings import BaseSettings
from typing import List
import json


class Settings(BaseSettings):
    # Database
    DATABASE_URL: str = "postgresql+asyncpg://crm_user:crm_password@db:5432/crm_db"

    # JWT Authentication
    SECRET_KEY: str = "your-secret-key-change-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    # OpenAI
    OPENAI_API_KEY: str = ""

    # Application
    DEBUG: bool = False
    BACKEND_CORS_ORIGINS: str = '["http://localhost:3000","http://localhost:5173"]'

    @property
    def cors_origins(self) -> List[str]:
        return json.loads(self.BACKEND_CORS_ORIGINS)

    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()
