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
