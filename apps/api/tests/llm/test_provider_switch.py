"""Task 1.2.4 — flipping the LLM provider is a config change, never a code change.

``LLM_PROVIDER`` (default ``groq``) selects the impl; setting it to ``gemini`` with a
fake ``GEMINI_API_KEY`` returns the Gemini impl with no code change. Each returned
provider structurally satisfies the :class:`LLMProvider` Protocol. ``disable_socket``
proves selection/construction does no network I/O.
"""

from __future__ import annotations

import pytest

from lengua_core.llm import get_provider
from lengua_core.llm.base import LLMProvider
from lengua_core.llm.fake import FakeLLM
from lengua_core.llm.gemini import GeminiProvider
from lengua_core.llm.groq import GroqProvider

pytestmark = pytest.mark.disable_socket


def test_default_provider_is_groq(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    monkeypatch.setenv("GROQ_API_KEY", "gsk_test_key")
    provider = get_provider()
    assert isinstance(provider, GroqProvider)
    assert isinstance(provider, LLMProvider)


def test_switch_to_gemini_via_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "gemini")
    monkeypatch.setenv("GEMINI_API_KEY", "fake-gemini-key")
    provider = get_provider()
    assert isinstance(provider, GeminiProvider)
    assert isinstance(provider, LLMProvider)


def test_explicit_name_overrides_env(monkeypatch: pytest.MonkeyPatch) -> None:
    # Env says groq, but an explicit argument wins — still no code change to swap.
    monkeypatch.setenv("LLM_PROVIDER", "groq")
    monkeypatch.setenv("GROQ_API_KEY", "gsk_test_key")
    monkeypatch.setenv("GEMINI_API_KEY", "fake-gemini-key")
    assert isinstance(get_provider("gemini"), GeminiProvider)


def test_fake_provider_needs_no_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    assert isinstance(get_provider("fake"), FakeLLM)
