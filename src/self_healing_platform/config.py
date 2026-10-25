"""Environment-driven application configuration."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

AppEnv = Literal["development", "demo", "production"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_name: str = "self-healing-devops-platform"
    app_version: str = "0.1.0"
    app_env: AppEnv = "development"
    log_level: str = "INFO"
    host: str = "0.0.0.0"  # nosec B104  # container bind; publish ports explicitly
    port: int = 8000

    database_url: str = "sqlite+pysqlite:///./data/app.sqlite"

    demo_failure_enabled: bool = False
    demo_auth_token: str = ""
    demo_max_duration_seconds: int = Field(default=60, ge=1, le=300)
    demo_max_failing_requests: int = Field(default=100, ge=1, le=1000)

    remediation_enabled: bool = False
    remediation_dry_run_only: bool = True
    remediation_auth_token: str = ""
    kubernetes_remediation_enabled: bool = False

    ai_summaries_enabled: bool = False
    ai_api_url: str = ""
    ai_api_token: str = ""
    ai_timeout_seconds: float = Field(default=8.0, ge=1.0, le=30.0)

    max_request_bytes: int = Field(default=65536, ge=1024, le=1_000_000)

    @field_validator("app_env", mode="before")
    @classmethod
    def normalize_env(cls, value: object) -> object:
        if isinstance(value, str):
            return value.lower()
        return value

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @property
    def demo_routes_allowed(self) -> bool:
        return self.app_env in {"development", "demo"} and self.demo_failure_enabled

    @property
    def sqlite_path(self) -> Path | None:
        if not self.database_url.startswith("sqlite"):
            return None
        # sqlite+pysqlite:///relative or sqlite+pysqlite:////absolute
        if ":///" not in self.database_url:
            return None
        raw = self.database_url.split(":///", 1)[1]
        if raw.startswith("/"):
            return Path(raw)
        return Path(raw)

    def ensure_sqlite_parent(self) -> None:
        path = self.sqlite_path
        if path is None:
            return
        path.parent.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    return Settings()


def clear_settings_cache() -> None:
    get_settings.cache_clear()
