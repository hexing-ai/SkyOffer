from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url


PROJECT_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    model_provider: str = "deepseek"
    model_name: str = "deepseek-chat"
    model_base_url: str = "https://api.deepseek.com"
    model_api_key: SecretStr | None = None
    model_timeout_seconds: float = Field(default=30.0, gt=0, le=120)
    model_max_retries: int = Field(default=1, ge=0, le=1)
    model_fallback_enabled: bool = True

    app_env: Literal["development", "test", "production"] = "development"
    app_version: str = "local"
    log_level: str = "INFO"
    log_format: Literal["text", "json"] = "text"
    app_port: int = Field(default=8001, ge=1024, le=65535)
    database_url: str = f"sqlite:///{PROJECT_ROOT / 'data' / 'skyoffer.db'}"
    database_pool_size: int = Field(default=5, ge=1, le=20)
    database_max_overflow: int = Field(default=5, ge=0, le=40)
    allowed_hosts: str = "127.0.0.1,localhost,testserver"
    trust_proxy_headers: bool = False
    rate_limit_enabled: bool = False
    rate_limit_requests: int = Field(default=10, ge=1, le=1000)
    rate_limit_window_seconds: int = Field(default=60, ge=1, le=3600)
    request_max_body_bytes: int = Field(default=131_072, ge=1024, le=1_048_576)

    @property
    def model_is_configured(self) -> bool:
        return bool(self.model_api_key and self.model_api_key.get_secret_value().strip())

    @property
    def allowed_host_list(self) -> list[str]:
        return [item.strip() for item in self.allowed_hosts.split(",") if item.strip()]

    def production_configuration_errors(self) -> list[str]:
        if self.app_env != "production":
            return []
        errors: list[str] = []
        if not self.model_is_configured:
            errors.append("MODEL_API_KEY must be configured")
        if urlsplit(self.model_base_url).scheme != "https":
            errors.append("MODEL_BASE_URL must use HTTPS")
        if make_url(self.database_url).get_backend_name() != "postgresql":
            errors.append("DATABASE_URL must use persistent PostgreSQL")
        if not self.allowed_host_list or "*" in self.allowed_host_list:
            errors.append("ALLOWED_HOSTS must be explicit")
        if not self.rate_limit_enabled:
            errors.append("RATE_LIMIT_ENABLED must be true")
        if not self.trust_proxy_headers:
            errors.append("TRUST_PROXY_HEADERS must be true behind the frontend proxy")
        if self.log_format != "json":
            errors.append("LOG_FORMAT must be json")
        if self.app_version.strip().lower() in {"", "local", "dev", "unknown"}:
            errors.append("APP_VERSION must identify an immutable release")
        return errors

    def assert_runtime_ready(self) -> None:
        errors = self.production_configuration_errors()
        if errors:
            raise ValueError("invalid production configuration: " + "; ".join(errors))


@lru_cache
def get_settings() -> Settings:
    return Settings()
