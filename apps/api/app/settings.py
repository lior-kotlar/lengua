"""Application settings, loaded from the environment via pydantic-settings.

Reads from the process environment and an optional ``.env`` file (see the repo-root
``.env.example`` for the documented variables). Only the variables the API service
actually needs are declared here; unrelated keys in ``.env`` are ignored.

Excluded from coverage (see ``[tool.coverage.run] omit`` in ``pyproject.toml``) — this
module is declarative configuration, not branching logic.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Typed view over the environment for the Lengua API."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ── LLM provider ──────────────────────────────────────────────────────────
    # Default to Groq for all dev/CI; flip to ``gemini`` for prod via env only.
    llm_provider: str = "groq"
    groq_model: str = "llama-3.1-8b-instant"
    groq_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash"
    gemini_api_key: str = ""

    # ── App ───────────────────────────────────────────────────────────────────
    env: str = "local"

    # ── Database / Supabase (declared so .env values validate; used in Phase 1+)
    database_url: str = ""
    supabase_url: str = ""
    supabase_anon_key: str = ""
    supabase_service_role_key: str = ""
    supabase_jwt_secret: str = ""


@lru_cache
def get_settings() -> Settings:
    """Return a cached, process-wide ``Settings`` instance."""
    return Settings()
