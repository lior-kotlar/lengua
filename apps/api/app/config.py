"""Application settings, read from the environment / a local ``.env`` file.

Operator-global config (the LLM provider, model, and key) lives here in the environment,
never in the database — users don't pick the provider. The provider defaults to Groq
(``llama-3.1-8b-instant``) for all dev/CI and is flipped to Gemini via ``LLM_PROVIDER``.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    llm_provider: str = "groq"
    llm_model: str = "llama-3.1-8b-instant"


@lru_cache
def get_settings() -> Settings:
    """Return a cached ``Settings`` instance for dependency injection."""
    return Settings()
