"""Tests for application settings defaults."""

import pytest

from app.config import Settings, get_settings


def test_llm_provider_defaults_to_groq(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    monkeypatch.delenv("LLM_MODEL", raising=False)
    settings = Settings(_env_file=None)
    assert settings.llm_provider == "groq"
    assert settings.llm_model == "llama-3.1-8b-instant"


def test_get_settings_is_cached() -> None:
    assert get_settings() is get_settings()
