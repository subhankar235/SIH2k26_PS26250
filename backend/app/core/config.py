"""Typed application settings loaded from environment variables."""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL, make_url


class Settings(BaseSettings):
    """Configure backend services and external connections."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    postgres_user: str = ""
    postgres_password: str = ""
    postgres_db: str = ""
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    kafka_bootstrap_servers: str = "localhost:9092"
    mlflow_tracking_uri: str = "http://localhost:5000"
    random_seed: int = 42
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:3000"])
    freshness_thresholds: dict[str, int]
    max_agent_retries: int = 3
    solver_time_limit_s: int = 30
    uncertainty_threshold: float = 0.35
    api_keys: dict[str, dict[str, str]] = Field(default_factory=dict)
    database_url_override: str | None = Field(
        default=None, validation_alias="DATABASE_URL", repr=False
    )

    @property
    def database_url(self) -> str:
        """Build a safely escaped PostgreSQL connection URL.

        Returns:
            A SQLAlchemy URL using the psycopg 3 driver.
        """
        if self.database_url_override:
            url = make_url(self.database_url_override)
            if url.drivername in {"postgres", "postgresql"}:
                url = url.set(drivername="postgresql+psycopg")
            if url.host and url.host.endswith(".neon.tech"):
                url = url.update_query_dict({"sslmode": "require"})
            return url.render_as_string(hide_password=False)

        if not self.postgres_user or not self.postgres_password or not self.postgres_db:
            raise ValueError(
                "Configure DATABASE_URL or all of POSTGRES_USER, POSTGRES_PASSWORD, and POSTGRES_DB"
            )
        return URL.create(
            "postgresql+psycopg",
            username=self.postgres_user,
            password=self.postgres_password,
            host=self.postgres_host,
            port=self.postgres_port,
            database=self.postgres_db,
        ).render_as_string(hide_password=False)


@lru_cache
def get_settings() -> Settings:
    """Load and cache settings from the process environment.

    Returns:
        The validated application settings.
    """
    return Settings()
