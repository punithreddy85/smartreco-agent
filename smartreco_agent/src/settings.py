"""Settings configuration for the SmartReco Agent.

Centralised configuration using Pydantic BaseSettings. Every credential is
read from the environment; nothing is ever hard-coded, logged, or rendered
into a template.
"""

from typing import Optional

from dotenv import load_dotenv
from pydantic import Field
from pydantic_settings import BaseSettings

from smartreco_agent.src.core.exceptions.exceptions import (
    AppException,
    AppExceptionCode,
)
from smartreco_agent.utils.pylogger import get_python_logger

logger = get_python_logger()

try:
    load_dotenv()
except Exception as e:  # pragma: no cover - defensive only
    logger.warning(f"Could not load .env file: {e}")


class Settings(BaseSettings):
    """Configuration settings for the SmartReco Agent."""

    # --- Server ---
    AGENT_HOST: str = Field(default="0.0.0.0", json_schema_extra={"env": "AGENT_HOST"})
    AGENT_PORT: int = Field(default=8000, json_schema_extra={"env": "AGENT_PORT"})
    PYTHON_LOG_LEVEL: str = Field(
        default="INFO", json_schema_extra={"env": "PYTHON_LOG_LEVEL"}
    )
    APP_BASE_URL: str = Field(
        default="http://localhost:8000",
        json_schema_extra={"env": "APP_BASE_URL"},
        description="Used to build absolute links (emails, pg_cron job definitions).",
    )

    # --- Database (Supabase Postgres, transaction pooler in production) ---
    DATABASE_URL: str = Field(
        default="postgresql://postgres:postgres@localhost:5432/smartreco",
        json_schema_extra={"env": "DATABASE_URL"},
    )
    DB_DISABLE_PREPARE: bool = Field(
        default=False,
        json_schema_extra={"env": "DB_DISABLE_PREPARE"},
        description="Must be true against the Supabase transaction pooler (port 6543), "
        "which does not support prepared statements. False for a direct local connection.",
    )
    DB_POOL_MIN_SIZE: int = Field(
        default=1, json_schema_extra={"env": "DB_POOL_MIN_SIZE"}
    )
    DB_POOL_MAX_SIZE: int = Field(
        default=10, json_schema_extra={"env": "DB_POOL_MAX_SIZE"}
    )

    # --- Mesh API (mandatory gateway for every LLM / embedding call) ---
    MESH_API_KEY: str = Field(default="", json_schema_extra={"env": "MESH_API_KEY"})
    MESH_BASE_URL: str = Field(
        default="https://api.meshapi.ai/v1",
        json_schema_extra={"env": "MESH_BASE_URL"},
    )
    MESH_CHAT_MODEL: str = Field(
        default="google/gemini-3-flash-preview",
        json_schema_extra={"env": "MESH_CHAT_MODEL"},
    )
    MESH_CHEAP_MODEL: str = Field(
        default="google/gemini-3-flash-preview",
        json_schema_extra={"env": "MESH_CHEAP_MODEL"},
    )
    MESH_EMBED_MODEL: str = Field(
        default="qwen/text-embedding-v4",
        json_schema_extra={"env": "MESH_EMBED_MODEL"},
    )
    MESH_EMBED_DIMENSIONS: int = Field(
        default=1536, json_schema_extra={"env": "MESH_EMBED_DIMENSIONS"}
    )

    # --- Auth / sessions ---
    SESSION_SECRET: str = Field(
        default="dev-secret-change-me", json_schema_extra={"env": "SESSION_SECRET"}
    )
    SESSION_COOKIE_NAME: str = Field(default="smartreco_session")
    SESSION_MAX_AGE_SECONDS: int = Field(default=60 * 60 * 24 * 14)  # 14 days

    # --- Cron ---
    CRON_SECRET: str = Field(
        default="dev-cron-secret-change-me", json_schema_extra={"env": "CRON_SECRET"}
    )

    # --- Email (scheduled digest bonus) ---
    RESEND_API_KEY: Optional[str] = Field(
        default=None, json_schema_extra={"env": "RESEND_API_KEY"}
    )
    RESEND_FROM_EMAIL: str = Field(
        default="SmartReco <onboarding@resend.dev>",
        json_schema_extra={"env": "RESEND_FROM_EMAIL"},
    )

    # --- Request logging ---
    REQUEST_LOGGING_ENABLED: bool = Field(default=True)

    # --- Trigger policy (ARCHITECTURE.md §8) ---
    TRIGGER_COOLDOWN_SECONDS: int = Field(
        default=600,
        json_schema_extra={"env": "TRIGGER_COOLDOWN_SECONDS"},
        description="Absolute minimum gap between agent runs for a user, even for "
        "an explicit manual refresh. Production default is 600s (10 min); lower "
        "this in local/demo .env files for faster feedback loops.",
    )
    TRIGGER_COUNT_THRESHOLD: int = Field(
        default=8, json_schema_extra={"env": "TRIGGER_COUNT_THRESHOLD"}
    )
    TRIGGER_DRIFT_THRESHOLD: float = Field(
        default=0.15, json_schema_extra={"env": "TRIGGER_DRIFT_THRESHOLD"}
    )

    @property
    def use_transaction_pooler(self) -> bool:
        """Whether the configured DATABASE_URL looks like a pooled connection."""
        return ":6543" in self.DATABASE_URL


def validate_config(settings: Settings) -> None:
    """Validate configuration settings that must hold before serving traffic."""
    if not (1024 <= settings.AGENT_PORT <= 65535):
        raise AppException(
            f"AGENT_PORT must be between 1024 and 65535, got {settings.AGENT_PORT}",
            AppExceptionCode.CONFIGURATION_VALIDATION_ERROR,
        )

    valid_log_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
    if settings.PYTHON_LOG_LEVEL.upper() not in valid_log_levels:
        raise AppException(
            f"PYTHON_LOG_LEVEL must be one of {valid_log_levels}, got {settings.PYTHON_LOG_LEVEL}",
            AppExceptionCode.CONFIGURATION_VALIDATION_ERROR,
        )

    if not settings.MESH_API_KEY:
        logger.warning(
            "MESH_API_KEY is not set - all agent generation and embedding calls will fail"
        )


settings = Settings()
