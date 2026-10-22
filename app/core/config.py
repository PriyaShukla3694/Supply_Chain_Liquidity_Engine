
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

    @property
    def cors_origin_list(self) -> list[str]:
        return [
            origin.strip()
            for origin in self.CORS_ORIGINS.split(",")
            if origin.strip()
        ]

    @model_validator(mode="after")
    def assemble_db_connection(self) -> "Settings":
        if not self.database_url:
            self.database_url = (
                f"postgresql://{self.postgres_user}:{self.postgres_password}"
                f"@localhost:5432/{self.postgres_db}"
            )
        return self

    @property
    def DATABASE_URL(self) -> str:
        return self.database_url


settings = Settings()
