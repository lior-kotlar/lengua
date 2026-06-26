"""Provider-agnostic LLM seam for Lengua.

The app talks to *some* LLM provider through the :class:`~lengua_core.llm.base.LLMProvider`
Protocol — never to a concrete vendor SDK directly. :func:`get_provider` picks the concrete
implementation from the ``LLM_PROVIDER`` env var:

- ``groq`` / ``gemini`` — the real providers (added in Phase 1; require an API key).
- ``fake`` — the deterministic :class:`~lengua_core.llm.fake.FakeLLM`, a pure function of its
  input with no network or randomness. Selected for unit/integration/E2E tests so CI never
  burns real quota.

The structured output models (:class:`GeneratedCard`, :class:`WordNote`) are re-exported here
from :mod:`lengua_core.models` so callers have a single import surface for the seam, along with the
key-resolution seam (:func:`resolve_llm_key`, task 3.9) and the persistent-transient error
(:class:`LLMTransientError`, task 3.5.2) the app layer maps to a friendly busy response.
"""

from __future__ import annotations

from lengua_core.models import GeneratedCard, WordNote

from .base import LLMProvider
from .keys import KeyUser, resolve_llm_key
from .provider import get_provider
from .retry import LLMTransientError

__all__ = [
    "GeneratedCard",
    "KeyUser",
    "LLMProvider",
    "LLMTransientError",
    "WordNote",
    "get_provider",
    "resolve_llm_key",
]
