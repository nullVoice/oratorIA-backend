"""Application settings, sourced from environment variables."""

from __future__ import annotations

from functools import lru_cache
from typing import Literal
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Runtime
    environment: Literal["development", "staging", "production", "test"] = "development"
    debug: bool = False
    secret_key: SecretStr = SecretStr("change-me")

    # Database
    database_url: str = "postgresql+asyncpg://oratoria:oratoria@localhost:5432/oratoria"
    database_echo: bool = False
    database_pool_size: int = 10
    database_max_overflow: int = 20

    @field_validator("database_url")
    @classmethod
    def _force_async_driver(cls, v: str) -> str:
        """Normalise managed-provider URLs (Neon/Render/Supabase) for asyncpg.

        Coerces `postgres://` / `postgresql://` to the async driver (otherwise
        SQLAlchemy picks psycopg2, which isn't installed), and rewrites libpq's
        query params that asyncpg rejects: `sslmode=require` -> `ssl=require`,
        and drops `channel_binding`.
        """
        if v.startswith("postgres://"):
            v = "postgresql+asyncpg://" + v[len("postgres://") :]
        elif v.startswith("postgresql://"):
            v = "postgresql+asyncpg://" + v[len("postgresql://") :]
        parts = urlsplit(v)
        if parts.query:
            kept = [
                ("ssl", val) if key == "sslmode" else (key, val)
                for key, val in parse_qsl(parts.query, keep_blank_values=True)
                if key != "channel_binding"
            ]
            v = urlunsplit(parts._replace(query=urlencode(kept)))
        return v

    # Redis / Celery
    redis_url: str = "redis://localhost:6379/0"
    celery_broker_url: str = "redis://localhost:6379/1"
    celery_result_backend: str = "redis://localhost:6379/2"

    # Auth
    jwt_secret: SecretStr = SecretStr("change-me-too")
    jwt_algorithm: str = "HS256"
    jwt_access_token_expires_minutes: int = 60
    jwt_refresh_token_expires_days: int = 30

    # LLM providers
    anthropic_api_key: SecretStr | None = None
    anthropic_model: str = "claude-sonnet-4-5"
    openai_api_key: SecretStr | None = None
    openai_model: str = "gpt-4o"

    # STT / TTS
    whisper_model: str = "whisper-1"
    deepgram_api_key: SecretStr | None = None
    elevenlabs_api_key: SecretStr | None = None
    elevenlabs_voice_id: str | None = None
    elevenlabs_model: str = "eleven_multilingual_v2"

    # Tavus CVI (avatar audience)
    tavus_api_key: SecretStr | None = None
    tavus_persona_id: str | None = None
    tavus_replica_id: str | None = None
    tavus_api_base_url: str = "https://tavusapi.com/v2"
    tavus_webhook_secret: SecretStr | None = None
    tavus_max_call_duration_seconds: int = 900  # 15 min per session
    tavus_callback_base_url: str | None = None  # e.g. https://api.oratoria.app
    persona_llm_secret: SecretStr | None = None  # shared secret for Tavus→persona LLM calls

    # Cloudflare R2
    r2_account_id: str | None = None
    r2_access_key_id: SecretStr | None = None
    r2_secret_access_key: SecretStr | None = None
    r2_bucket: str = "oratoria"
    r2_endpoint_url: str | None = None

    # Payments
    stripe_secret_key: SecretStr | None = None
    stripe_webhook_secret: SecretStr | None = None
    stripe_price_basic: str | None = None
    stripe_price_pro: str | None = None
    culqi_public_key: str | None = None
    culqi_secret_key: SecretStr | None = None

    # Email
    resend_api_key: SecretStr | None = None
    resend_from: str = "no-reply@oratoria.app"

    # Observability
    sentry_dsn: str | None = None
    langfuse_public_key: SecretStr | None = None
    langfuse_secret_key: SecretStr | None = None
    langfuse_host: str = "https://cloud.langfuse.com"

    # CORS
    cors_origins: str = "http://localhost:3000,http://localhost:5173"
    # Regex for origins allowed in addition to cors_origins. Defaults to any
    # Vercel deployment of the frontend project, so deployment-specific URLs
    # (e.g. orator-ia-frontend-<hash>.vercel.app) work, not just the alias.
    # Anchored (^…$) so Starlette's fullmatch can't be tricked by a suffix like
    # https://orator-ia-frontend-x.vercel.app.evil.com.
    cors_origin_regex: str = r"^https://orator-ia-frontend-[a-z0-9-]+\.vercel\.app$"

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @model_validator(mode="after")
    def _enforce_strong_secrets_in_prod(self) -> Settings:
        """Fail fast if auth secrets are weak/default in production.

        Render injects strong generated values, so prod is fine; this guards
        against an accidental deploy that boots with the public 'change-me'
        defaults, which would let anyone forge valid JWTs.
        """
        if self.environment == "production":
            for name in ("secret_key", "jwt_secret"):
                raw = getattr(self, name).get_secret_value()
                if raw in ("change-me", "change-me-too") or len(raw) < 32:
                    raise ValueError(
                        f"{name} must be set to a strong (>=32 char) value in production"
                    )
        return self


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
