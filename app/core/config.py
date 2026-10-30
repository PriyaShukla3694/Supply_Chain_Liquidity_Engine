
from datetime import date
from typing import Optional

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
        env_ignore_empty=True,
    )

    postgres_user: str = "postgres"
    postgres_password: str = "postgres"
    postgres_db: str = "liquidity_engine"
    database_url: Optional[str] = None

    # Historical business date for the dataset
    REFERENCE_DATE: Optional[date] = None

    JWT_SECRET: str = "supersecretjwtkeyforlocaldevelopmentonly12345"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60

    CORS_ORIGINS: str = "http://localhost:5173,http://localhost:3000"

    # RAG / LLM configuration
    OPENAI_API_KEY: Optional[str] = None
    OPENAI_MODEL: Optional[str] = None
    EMBEDDING_MODEL: str = "sentence-transformers/all-MiniLM-L6-v2"

    @property
    def cors_origin_list(self) -> list[str]:
        return [
            origin.strip()
            for origin in self.CORS_ORIGINS.split(",")
            if origin.strip()
        ]

    @model_validator(mode="after")
    def assemble_db_connection(self) -> "Settings":
        # No automatic fallback; DATABASE_URL must be provided via env or default values.
        return self

    @property
    def DATABASE_URL(self) -> str:
        return self.database_url


settings = Settings()
