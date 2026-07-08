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

from lengua_core.llm.retry import MAX_WORDS_PER_REQUEST


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

    # ── LLM cost guard — global concurrency cap (Phase 3.5) ───────────────────
    # The maximum number of provider (LLM) calls allowed in flight across the whole process at once,
    # enforced by a global asyncio semaphore (``app.llm_runner``). Bounds load on the provider's
    # free tier AND caps the kill-switch's read-then-increment overshoot (the budget gate reads
    # before the call and increments after success, so the worst-case overshoot is the number of
    # in-flight calls — this value). Over the cap, a request waits briefly then gets a friendly 503
    # ``server_busy`` rather than queuing unbounded. NOTE: this is per-process; safe horizontal
    # scale-out beyond one instance additionally needs the distributed rate limiter (Phase 6).
    llm_max_concurrency: int = 4

    # ── LLM cost guard — request-size + reuse caps (Phase 3.6) ────────────────
    # Hard ceiling on the number of vocabulary words a single ``/generate`` request may carry. It is
    # surfaced here (defaulting to the shared ``lengua_core.llm.retry.MAX_WORDS_PER_REQUEST`` value
    # the providers already cap at) so it is env-overridable; the ``/generate`` request schema
    # rejects an over-limit list with **422** (a hard reject, not silent truncation) — bounding
    # prompt size and cost.
    max_words_per_request: int = MAX_WORDS_PER_REQUEST
    # Short reuse window (seconds) for ``/discover`` previews: a repeated discover for the same
    # ``(user, language, topic, count)`` within this window returns the PRIOR preview from an
    # in-process cache WITHOUT a fresh provider call (and without burning a daily-cap/budget count)
    # — the cheapest call is the one we don't make. In-process today (single instance); the
    # distributed (Postgres/Upstash) swap is a Phase-6 concern (see ``app/discover_cache.py``), the
    # same caveat family as the in-process rate limiter.
    discover_reuse_window_seconds: int = 300

    # ── LLM cost guard — per-user rate limit (Phase 3.3) ──────────────────────
    # Per-user sliding-window request ceiling, counted across ALL gated LLM kinds (generate /
    # discover / explain). Smooths bursts against the provider's RPM ceiling — distinct from the
    # per-kind *daily* caps above. In-process today (single instance); the distributed swap is a
    # Phase-6 concern (see ``app/ratelimit.py``).
    rate_limit_per_min: int = 10

    # ── LLM cost guard — signup-abuse day-0 guard (Phase 3.7) ─────────────────
    # A freshly-created account (its ``profiles.created_at`` falls on the current UTC day) gets a
    # reduced first-day ``generate`` ceiling, so a burst of throwaway signups can't drain the shared
    # operator key on day one. The effective generate cap is ``min(resolved_cap, this)``;
    # established accounts use their normal cap.
    new_account_day0_generate_cap: int = 5

    # ── LLM cost guard — global daily budget kill-switch (Phase 3.4) ──────────
    # The project-wide ceiling on SUCCESSFUL LLM calls per day, summed across ALL users — the
    # "I will never get a bill" backstop. It is the LAST gate (after the per-user daily cap); once
    # the global ``llm_budget`` counter reaches this for the UTC day, every gated LLM call is denied
    # with the friendly ``daily_limit_reached`` message until the day rolls over. Set this BELOW the
    # active provider's free-tier requests-per-day (RPD) ÷ the max retry attempts (``retry.py``
    # ``DEFAULT_MAX_ATTEMPTS`` = 3): one *counted* call can fan out to up to 3 real provider calls
    # on 429/5xx, so RPD/3 bounds the worst case. Groq ``llama-3.1-8b-instant``'s free tier is a few
    # thousand/day, so the default 1000 (≤3000 worst-case requests) stays well under it. (Counters
    # bump only on a successful call, so concurrent in-flight requests may overshoot slightly —
    # bounded by ``LLM_MAX_CONCURRENCY``; acceptable as the budget sits far below the free RPD.)
    global_daily_budget: int = 1000

    # ── Feature flags (Phase 6.9) ─────────────────────────────────────────────
    # How long (seconds) the in-process feature-flag accessor (``app.feature_flags``) caches the
    # ``feature_flags`` table snapshot before re-reading it. A short TTL is what lets an operator
    # toggle a flag in prod by writing the table and have it take effect WITHOUT a redeploy: the
    # change is picked up within this window (default ~30s). Set 0 to disable caching (re-read every
    # resolution). The clock is injectable so the TTL refresh is deterministic in tests.
    feature_flag_ttl_seconds: int = 30

    # ── DB-backed prompts (GitHub #80) ────────────────────────────────────────
    # How long (seconds) the in-process prompt store (``app.prompt_store``) caches the resolved
    # ACTIVE prompt versions before re-reading ``prompt_versions``. A short TTL is what lets an
    # operator change a prompt in prod (append a new active version) and have generation pick it up
    # WITHOUT a redeploy: the change is picked up within this window (default ~60s). The clock is
    # injectable so the TTL refresh is deterministic in tests, exactly like the feature-flag store.
    prompt_cache_ttl_seconds: int = 60

    # ── App ───────────────────────────────────────────────────────────────────
    env: str = "local"

    # ── Error tracking — Sentry (Phase 5.4.1) ─────────────────────────────────
    # Backend Sentry DSN. Sentry is initialised ONLY when this is set (``app.error_tracking``),
    # mirroring the OTLP-exporter discipline: unset → a no-op with zero network egress (the
    # local/CI/E2E path). The web app uses a SEPARATE, browser-safe DSN (``VITE_SENTRY_DSN_WEB`` in
    # ``apps/web/.env``). Documented in the repo-root ``.env.example``.
    sentry_dsn_api: str = ""

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

    # ── Transactional email (Phase 8, task 8.3.1) ─────────────────────────────
    # Resend API key for outbound mail — today only the public /delete-account confirmation link.
    # Unset → ``LoggingMailer`` (no egress; the local/CI/E2E path and the prod path until the owner
    # configures Resend, issue #103). Set → ``ResendMailer`` sends for real. Typed ``SecretStr`` so
    # it is masked in repr/logs. Mirrors the LLM seam: a config flip, never a code change.
    resend_api_key: SecretStr = SecretStr("")
    # The From address for that mail (used only when a mail provider is configured).
    email_from: str = "Lengua <privacy@lengua.app>"
    # Public web origin used to build ABSOLUTE links in outbound mail (the /delete-account confirm
    # URL). Empty in dev/CI (mail is suppressed there anyway); set to the real prod web host at
    # cutover so the emailed confirmation link is clickable.
    public_web_url: str = ""

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
