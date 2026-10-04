"""Application configuration (12-factor, environment driven)."""
from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

    app_name: str = "JobApply AI"
    environment: str = "development"  # development | staging | production | test
    debug: bool = False
    public_base_url: str = "http://localhost:3000"
    api_base_url: str = "http://localhost:8000"
    cors_origins: str = "http://localhost:3000"

    # --- database / queue / storage
    database_url: str = "sqlite:///./jobapply.db"
    redis_url: str = "redis://localhost:6379/0"
    task_mode: str = "inline"  # inline | celery
    storage_backend: str = "local"  # local | s3
    storage_local_path: str = "./storage"
    s3_endpoint_url: str | None = None
    s3_bucket: str = "jobapply"
    s3_region: str = "us-east-1"
    s3_access_key: str | None = None
    s3_secret_key: str | None = None

    # --- secrets (MUST be overridden outside development)
    secret_key: str = "dev-only-change-me-dev-only-change-me-0123456789"
    encryption_key: str = ""  # urlsafe base64 32 bytes (Fernet). Generated for dev if empty.
    access_token_minutes: int = 15
    admin_session_minutes: int = 30
    admin_secret_key: str = "dev-only-admin-secret-change-me-0123456789"
    refresh_token_days: int = 30
    signed_url_seconds: int = 300
    confirmation_token_minutes: int = 15
    require_verified_email_to_send: bool = True

    # --- upload limits
    max_upload_mb: int = 10
    max_bulk_jobs: int = 60

    # --- AI
    ai_provider: str = "heuristic"  # heuristic | openai | anthropic | gemini | openai_compatible
    ai_fallback_to_heuristic: bool = True
    ai_cheap_model: str = ""
    ai_strong_model: str = ""
    ai_max_input_chars: int = 24_000
    ai_max_output_tokens: int = 2_000
    ai_max_retries: int = 2
    openai_api_key: str | None = None
    openai_base_url: str = "https://api.openai.com/v1"
    anthropic_api_key: str | None = None
    gemini_api_key: str | None = None
    ai_training_opt_in_default: bool = False

    # --- OAuth
    google_client_id: str | None = None
    google_client_secret: str | None = None
    microsoft_client_id: str | None = None
    microsoft_client_secret: str | None = None
    microsoft_tenant: str = "common"

    # --- system email (transactional)
    system_smtp_host: str | None = None
    system_smtp_port: int = 587
    system_smtp_user: str | None = None
    system_smtp_password: str | None = None
    system_email_from: str = "no-reply@jobapply.local"
    sentry_dsn: str | None = None

    # --- abuse prevention / limits (defaults; plan limits override)
    rate_limit_backend: str = "memory"  # memory | redis (use redis when running more than one API process)
    trusted_proxy_hops: int = 0  # proxies you control in front of the API; 0 = ignore X-Forwarded-For
    rate_limit_per_minute: int = 120
    auth_rate_limit_per_minute: int = 10
    email_send_per_hour: int = 15
    email_send_per_day: int = 40
    url_fetch_timeout_seconds: int = 10
    url_fetch_max_bytes: int = 2_000_000

    def is_production(self) -> bool:
        return self.environment == "production"


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    if s.is_production():
        if s.secret_key.startswith("dev-only") or len(s.secret_key) < 32:
            raise RuntimeError("SECRET_KEY must be set to a strong random value in production")
        if s.admin_secret_key.startswith("dev-only") or len(s.admin_secret_key) < 32:
            raise RuntimeError("ADMIN_SECRET_KEY must be set to a strong random value in production")
        if not s.encryption_key:
            raise RuntimeError("ENCRYPTION_KEY must be set in production")
    return s
