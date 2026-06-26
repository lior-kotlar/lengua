"""Application settings, loaded from the environment via pydantic-settings.

Reads from the process environment and an optional ``.env`` file (see the repo-root
``.env.example`` for the documented variables). Only the variables the API service
actually needs are declared here; unrelated keys in ``.env`` are ignored.

Excluded from coverage (see ``[tool.coverage.run] omit`` in ``pyproject.toml``) — this
module is declarative configuration, not branching logic.
"""

from functools import lru_cache
from typing import Annotated

from pydantic import field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


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
    # Supabase JWT verification (Phase 2.3). HS256 shared secret is the default; set the JWKS URL
    # to verify asymmetric (RS256/ES256) "JWT signing keys" instead. ``aud`` is the audience the
    # backend requires (Supabase signs access tokens with ``authenticated``).
    supabase_jwt_secret: str = ""
    supabase_jwks_url: str = ""
    supabase_jwt_aud: str = "authenticated"

    # ── CORS (Phase 2.3.4) ────────────────────────────────────────────────────
    # Allowlisted browser/app origins for cross-origin requests. Accepts a JSON array or a
    # comma-separated string in the environment (``CORS_ALLOW_ORIGINS=https://a,https://b``).
    # Defaults cover local web dev + the Capacitor app scheme; prod origins are added via env.
    cors_allow_origins: Annotated[list[str], NoDecode] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "capacitor://localhost",
    ]

    @field_validator("cors_allow_origins", mode="before")
    @classmethod
    def _split_origins(cls, value: object) -> object:
        """Allow a comma-separated string (env) as well as a real list / JSON array."""
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value


@lru_cache
def get_settings() -> Settings:
    """Return a cached, process-wide ``Settings`` instance."""
    return Settings()
