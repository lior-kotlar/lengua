"""Task 1.1.5 — configuration: typed settings + secret-free domain constants.

Asserts the typed :class:`app.settings.Settings` defaults (``LLM_PROVIDER == "groq"``), that the
domain :mod:`lengua_core.config` holds only non-secret tuning constants (no provider keys), and
that provider selection fails fast on a misconfigured ``LLM_PROVIDER`` (the seam's fail-fast
floor; the per-provider key check lands with the real providers in task 1.2.1).
"""

from __future__ import annotations

import pytest

from app.settings import Settings
from lengua_core import config
from lengua_core.llm import get_provider
from lengua_core.llm.fake import FakeLLM


def test_llm_provider_defaults_to_groq(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    settings = Settings(_env_file=None)  # type: ignore[call-arg]
    assert settings.llm_provider == "groq"


def test_groq_model_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GROQ_MODEL", raising=False)
    settings = Settings(_env_file=None)  # type: ignore[call-arg]
    assert settings.groq_model == "llama-3.1-8b-instant"


def test_domain_config_has_no_secret_constants() -> None:
    # Secrets (provider key/model) left the domain core for app.settings / env in 1.1.5.
    assert not hasattr(config, "GEMINI_API_KEY")
    assert not hasattr(config, "MODEL")


def test_domain_config_keeps_non_secret_tuning_constants() -> None:
    assert config.CEFR_BANDS == ["A1", "A2", "B1", "B2", "C1", "C2"]
    assert config.LEVEL_MIN == 0.0
    assert config.LEVEL_MAX == 6.0
    assert set(config.LEVEL_DELTAS) == {1, 2, 3, 4}
    # The legacy SQLite DB path is retained for the legacy Streamlit app.
    assert str(config.DB_PATH).endswith("lengua.db")


def test_get_provider_fake_needs_no_key() -> None:
    assert isinstance(get_provider("fake"), FakeLLM)


def test_get_provider_fails_fast_on_unknown_provider() -> None:
    with pytest.raises(ValueError, match="Unknown LLM provider"):
        get_provider("not-a-provider")


def test_get_provider_real_providers_fail_fast_without_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The real impls landed in task 1.2 and fail fast when their API key is unset.
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    for name in ("groq", "gemini"):
        with pytest.raises(RuntimeError):
            get_provider(name)


# ── Task 3.2.1 — typed per-user daily-cap quota config ────────────────────────
_QUOTA_ENV_VARS = (
    "MAX_GENERATE_PER_DAY",
    "MAX_DISCOVER_PER_DAY",
    "MAX_EXPLAIN_PER_DAY",
    "DEFAULT_GENERATE_PER_DAY",
    "DEFAULT_DISCOVER_PER_DAY",
    "DEFAULT_EXPLAIN_PER_DAY",
)


def test_quota_ceilings_load(monkeypatch: pytest.MonkeyPatch) -> None:
    """The six daily-cap ceilings fall back to their documented defaults and load from env."""
    # Defaults (no env): the conservative finalized values (outstanding-work.md §9 + .env.example).
    for var in _QUOTA_ENV_VARS:
        monkeypatch.delenv(var, raising=False)
    defaults = Settings(_env_file=None)  # type: ignore[call-arg]
    assert defaults.max_generate_per_day == 50
    assert defaults.max_discover_per_day == 30
    assert defaults.max_explain_per_day == 100
    assert defaults.default_generate_per_day == 20
    assert defaults.default_discover_per_day == 10
    assert defaults.default_explain_per_day == 50
    # Every per-user default is <= its hard server maximum (a user can never default above the cap).
    assert defaults.default_generate_per_day <= defaults.max_generate_per_day
    assert defaults.default_discover_per_day <= defaults.max_discover_per_day
    assert defaults.default_explain_per_day <= defaults.max_explain_per_day

    # Env overrides win (UPPER_SNAKE of each field).
    monkeypatch.setenv("MAX_GENERATE_PER_DAY", "7")
    monkeypatch.setenv("DEFAULT_EXPLAIN_PER_DAY", "3")
    overridden = Settings(_env_file=None)  # type: ignore[call-arg]
    assert overridden.max_generate_per_day == 7
    assert overridden.default_explain_per_day == 3
    # Untouched ones still fall back to defaults.
    assert overridden.max_discover_per_day == 30


# ── Tasks 3.3.2 / 3.7.2 — rate-limit + signup-abuse day-0 config ──────────────
def test_rate_limit_and_day0_caps_load(monkeypatch: pytest.MonkeyPatch) -> None:
    """The per-minute rate limit and day-0 generate cap fall back to defaults and load from env."""
    for var in ("RATE_LIMIT_PER_MIN", "NEW_ACCOUNT_DAY0_GENERATE_CAP"):
        monkeypatch.delenv(var, raising=False)
    defaults = Settings(_env_file=None)  # type: ignore[call-arg]
    assert defaults.rate_limit_per_min == 10
    assert defaults.new_account_day0_generate_cap == 5

    monkeypatch.setenv("RATE_LIMIT_PER_MIN", "25")
    monkeypatch.setenv("NEW_ACCOUNT_DAY0_GENERATE_CAP", "2")
    overridden = Settings(_env_file=None)  # type: ignore[call-arg]
    assert overridden.rate_limit_per_min == 25
    assert overridden.new_account_day0_generate_cap == 2


# ── Task 3.4.1 — global daily budget kill-switch config ───────────────────────
def test_global_budget_loads(monkeypatch: pytest.MonkeyPatch) -> None:
    """``GLOBAL_DAILY_BUDGET`` falls back to its documented default and loads from env."""
    monkeypatch.delenv("GLOBAL_DAILY_BUDGET", raising=False)
    defaults = Settings(_env_file=None)  # type: ignore[call-arg]
    # The conservative default — comfortably below the active provider's free RPD (.env.example).
    assert defaults.global_daily_budget == 1000

    monkeypatch.setenv("GLOBAL_DAILY_BUDGET", "3")
    overridden = Settings(_env_file=None)  # type: ignore[call-arg]
    assert overridden.global_daily_budget == 3
