"""Selecting the active LLM provider from configuration.

:func:`get_provider` maps the ``LLM_PROVIDER`` env var to a concrete
:class:`~lengua_core.llm.base.LLMProvider`. Only ``fake`` is wired in Phase 0 (it needs no API
key and does no I/O); the real ``groq`` / ``gemini`` providers are recognised but raise until
they are implemented in Phase 1, so a typo in the env var fails loudly instead of silently
falling back.
"""

from __future__ import annotations

import os

from .base import LLMProvider
from .fake import FakeLLM

# Providers planned for Phase 1. Listed here so an unset/typo'd value gives a precise error
# (``not yet implemented`` vs ``unknown``) without importing any vendor SDK.
_PLANNED_REAL = frozenset({"groq", "gemini"})


def get_provider(name: str | None = None) -> LLMProvider:
    """Return the active :class:`LLMProvider`.

    ``name`` defaults to the ``LLM_PROVIDER`` env var (falling back to ``groq``, matching the
    app settings default). ``fake`` returns the deterministic :class:`FakeLLM`. The real
    providers are not built yet and raise :class:`NotImplementedError`; any other value raises
    :class:`ValueError`.
    """
    resolved = (name or os.getenv("LLM_PROVIDER", "groq")).strip().lower()
    if resolved == "fake":
        return FakeLLM()
    if resolved in _PLANNED_REAL:
        raise NotImplementedError(
            f"LLM provider {resolved!r} is not implemented yet (Phase 1). "
            "Set LLM_PROVIDER=fake for tests."
        )
    raise ValueError(
        f"Unknown LLM provider {resolved!r}. Expected one of: fake, groq, gemini."
    )
