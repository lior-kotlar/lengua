"""Task 1.2.1 — ``get_provider`` reads ``LLM_PROVIDER`` once and fails fast.

An unknown provider name raises ``ValueError``; selecting a real provider without its
API key raises a clear ``RuntimeError`` (so a misconfigured deployment dies at startup,
not on the first LLM call). Runs under ``disable_socket`` — provider construction must
do no network I/O (the SDK client is built lazily, on first call).
"""

from __future__ import annotations

import pytest

from lengua_core.llm import get_provider
from lengua_core.llm.gemini import GeminiProvider
from lengua_core.llm.groq import GroqProvider

pytestmark = pytest.mark.disable_socket


def test_unknown_provider_name_raises() -> None:
    with pytest.raises(ValueError, match="Unknown LLM provider"):
        get_provider("does-not-exist")


def test_unknown_provider_from_env_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "totally-bogus")
    with pytest.raises(ValueError, match="Unknown LLM provider"):
        get_provider()


def test_missing_groq_key_raises_clear_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "groq")
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="GROQ_API_KEY"):
        get_provider()


def test_missing_gemini_key_raises_clear_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="GEMINI_API_KEY"):
        get_provider("gemini")


def test_groq_built_when_key_present(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "groq")
    monkeypatch.setenv("GROQ_API_KEY", "gsk_test_key")
    monkeypatch.setenv("GROQ_MODEL", "llama-3.1-8b-instant")
    provider = get_provider()
    assert isinstance(provider, GroqProvider)
    assert provider.model == "llama-3.1-8b-instant"


def test_gemini_built_when_key_present(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "fake-gemini-key")
    monkeypatch.setenv("GEMINI_MODEL", "gemini-2.5-flash")
    provider = get_provider("gemini")
    assert isinstance(provider, GeminiProvider)
    assert provider.model == "gemini-2.5-flash"
