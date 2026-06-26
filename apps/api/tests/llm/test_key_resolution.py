"""Task 3.9.1 — ``resolve_llm_key`` is the single operator-key chokepoint.

The resolver returns the operator env key for *any* user (the BYOK ``user`` override is inert
today), and a grep proves no other module in the LLM seam reads the operator key env vars directly —
only the resolver does. Runs under ``disable_socket`` (the resolver reads env only).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from lengua_core.llm import resolve_llm_key
from lengua_core.llm.keys import _OPERATOR_KEY_ENV

pytestmark = pytest.mark.disable_socket

#: The operator-key env vars that must be read *only* through the resolver module.
_KEY_ENV_VARS = ("GROQ_API_KEY", "GEMINI_API_KEY")


class _FakeUser:
    """A stand-in BYOK handle (carries ``plan``) — accepted but ignored by the resolver today."""

    plan = "paid"


def test_operator_key_only(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "groq")
    monkeypatch.setenv("GROQ_API_KEY", "gsk_operator_key")

    # The resolver returns the operator env key for the active provider — for no user, an explicit
    # ``None``, and an actual (BYOK-shaped) user alike: the ``user`` override is inert today.
    assert resolve_llm_key() == "gsk_operator_key"
    assert resolve_llm_key(None) == "gsk_operator_key"
    assert resolve_llm_key(_FakeUser()) == "gsk_operator_key"


def test_explicit_provider_overrides_llm_provider_env(monkeypatch: pytest.MonkeyPatch) -> None:
    # A provider passes its own name explicitly, so it resolves its own key regardless of the active
    # LLM_PROVIDER (this is how GeminiProvider.from_env() always reads GEMINI_API_KEY).
    monkeypatch.setenv("LLM_PROVIDER", "groq")
    monkeypatch.setenv("GEMINI_API_KEY", "gemini_operator_key")
    assert resolve_llm_key(provider="gemini") == "gemini_operator_key"


def test_missing_key_raises_runtime_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "groq")
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="GROQ_API_KEY"):
        resolve_llm_key()


def test_blank_key_raises_runtime_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "gemini")
    monkeypatch.setenv("GEMINI_API_KEY", "")
    with pytest.raises(RuntimeError, match="GEMINI_API_KEY"):
        resolve_llm_key()


def test_unknown_provider_raises_value_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    with pytest.raises(ValueError, match="No operator key"):
        resolve_llm_key(provider="does-not-exist")


def test_known_provider_env_map() -> None:
    # Documents the seam's responsibility: exactly the two real providers map to their key env vars.
    assert _OPERATOR_KEY_ENV == {"groq": "GROQ_API_KEY", "gemini": "GEMINI_API_KEY"}


def _llm_pkg_dir() -> Path:
    """``apps/api/lengua_core/llm`` — the LLM seam package (the 'client') being grepped."""
    return Path(__file__).resolve().parents[2] / "lengua_core" / "llm"


def test_only_resolver_module_reads_key_env_vars() -> None:
    """Grep the LLM seam: the key env-var names appear in exactly one module — the resolver.

    This is the structural guarantee of task 3.9.1: the LLM client takes its key only from
    ``resolve_llm_key`` (``keys.py``), so a future BYOK path has a single override point and no
    other module reads ``GROQ_API_KEY`` / ``GEMINI_API_KEY`` directly.
    """
    offenders: dict[str, list[str]] = {}
    for path in sorted(_llm_pkg_dir().glob("*.py")):
        text = path.read_text(encoding="utf-8")
        hits = [var for var in _KEY_ENV_VARS if var in text]
        if hits:
            offenders[path.name] = hits

    assert set(offenders) == {"keys.py"}, (
        f"operator key env vars must be read only via resolve_llm_key (keys.py); found: {offenders}"
    )
