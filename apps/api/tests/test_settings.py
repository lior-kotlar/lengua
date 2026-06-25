"""Tests for the pydantic-settings configuration module."""

import pytest

from app.settings import Settings


def test_llm_provider_defaults_to_groq(monkeypatch: pytest.MonkeyPatch) -> None:
    """With nothing in the environment, LLM_PROVIDER falls back to ``groq``."""
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    # Bypass any local .env so we exercise the in-code default, not a file value.
    settings = Settings(_env_file=None)  # type: ignore[call-arg]
    assert settings.llm_provider == "groq"


def test_groq_model_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GROQ_MODEL", raising=False)
    settings = Settings(_env_file=None)  # type: ignore[call-arg]
    assert settings.groq_model == "llama-3.1-8b-instant"


def test_env_overrides_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "gemini")
    settings = Settings(_env_file=None)  # type: ignore[call-arg]
    assert settings.llm_provider == "gemini"
