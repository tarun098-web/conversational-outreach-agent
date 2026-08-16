from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "Conversational Outreach Agent"
    app_env: Literal["development", "test", "production"] = "development"
    app_base_url: str = "http://localhost:8000"
    secret_key: str = "development-only-change-me"
    log_level: str = "INFO"

    ai_provider: Literal["mock", "groq"] = "mock"
    email_provider: Literal["mock", "gmail"] = "mock"
    storage_provider: Literal["memory", "supabase"] = "memory"

    groq_api_key: str | None = None
    groq_fast_model: str = "openai/gpt-oss-20b"
    groq_smart_model: str = "openai/gpt-oss-120b"
    groq_safety_model: str = "openai/gpt-oss-safeguard-20b"

    supabase_url: str | None = None
    supabase_key: str | None = None

    gmail_credentials_path: Path = Path(".runtime/credentials.json")
    gmail_token_path: Path = Path(".runtime/token.json")
    gmail_pubsub_audience: str | None = None
    gmail_pubsub_verification_token: str | None = None

    enable_background_polling: bool = False
    max_context_messages: int = Field(default=20, ge=1, le=100)
    require_human_approval: bool = True

    @model_validator(mode="after")
    def validate_provider_credentials(self) -> "Settings":
        if self.ai_provider == "groq" and not self.groq_api_key:
            raise ValueError("GROQ_API_KEY is required when AI_PROVIDER=groq")
        if self.storage_provider == "supabase" and not (self.supabase_url and self.supabase_key):
            raise ValueError(
                "SUPABASE_URL and SUPABASE_KEY are required when STORAGE_PROVIDER=supabase"
            )
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
