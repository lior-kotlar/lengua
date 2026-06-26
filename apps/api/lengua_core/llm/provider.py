"""Selecting the active LLM provider from configuration.

:func:`get_provider` maps the ``LLM_PROVIDER`` env var to a concrete
:class:`~lengua_core.llm.base.LLMProvider`:

- ``groq`` (default) -> :class:`~lengua_core.llm.groq.GroqProvider` (OpenAI-compatible
  JSON mode); requires the Groq operator key.
- ``gemini`` -> :class:`~lengua_core.llm.gemini.GeminiProvider` (native schema output,
  reserved for prod); requires the Gemini operator key.
- ``fake`` -> the deterministic :class:`~lengua_core.llm.fake.FakeLLM` (no key, no I/O).

The selected provider's key is checked **once, eagerly** (each provider's ``from_env`` obtains it
through the single :func:`~lengua_core.llm.keys.resolve_llm_key` seam, which fails fast with a clear
error), so a misconfigured deployment dies at startup rather than on the first LLM call. The vendor
SDKs are imported lazily — only the chosen provider's SDK is loaded, and the ``fake`` path pulls in
neither.
"""

from __future__ import annotations

import os

from .base import LLMProvider
from .fake import FakeLLM


def get_provider(name: str | None = None) -> LLMProvider:
    """Return the active :class:`LLMProvider`.

    ``name`` defaults to the ``LLM_PROVIDER`` env var (falling back to ``groq``, the
    app-settings default). An unknown value raises :class:`ValueError`; a real provider
    selected without its API key raises :class:`RuntimeError` (fail-fast at startup).
    """
    resolved = (name or os.getenv("LLM_PROVIDER", "groq")).strip().lower()
    if resolved == "fake":
        return FakeLLM()
    if resolved == "groq":
        from .groq import GroqProvider

        return GroqProvider.from_env()
    if resolved == "gemini":
        from .gemini import GeminiProvider

        return GeminiProvider.from_env()
    raise ValueError(
        f"Unknown LLM provider {resolved!r}. Expected one of: fake, groq, gemini."
    )
