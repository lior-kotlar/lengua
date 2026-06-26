"""Application settings, loaded from the environment via pydantic-settings.

Reads from the process environment and an optional ``.env`` file (see the repo-root
``.env.example`` for the documented variables). Only the variables the API service
actually needs are declared here; unrelated keys in ``.env`` are ignored.

Excluded from coverage (see ``[tool.coverage.run] omit`` in ``pyproject.toml``) — this
module is declarative configuration, not branching logic.
"""

from functools import lru_cache
from typing import Annotated

from pydantic import SecretStr, field_validator
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

    # ── LLM cost guard — per-user daily caps (Phase 3.2) ──────────────────────
    # Hard server maxima per LLM ``kind``: a user can never exceed these even by raising their own
    # per-user cap in ``user_settings`` (``resolve_user_cap`` clamps the user value with ``min()``).
    max_generate_per_day: int = 50
    max_discover_per_day: int = 30
    max_explain_per_day: int = 100
    # Per-user defaults applied when ``user_settings`` carries no (or a blank/non-numeric) override
    # for that kind. Always ``<=`` the matching server maximum above.
    default_generate_per_day: int = 20
    default_discover_per_day: int = 10
    default_explain_per_day: int = 50

    # ── App ───────────────────────────────────────────────────────────────────
    env: str = "local"

    # ── Database / Supabase (declared so .env values validate; used in Phase 1+)
    database_url: str = ""
    supabase_url: str = ""
    supabase_anon_key: str = ""
    # The RLS-bypassing "god-mode" Admin key (used only by the account-deletion path). Typed as
    # ``SecretStr`` so it is masked in any ``repr``/log/traceback and can never be accidentally
    # serialized; read it back with ``.get_secret_value()`` at the single call site.
    supabase_service_role_key: SecretStr = SecretStr("")
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
