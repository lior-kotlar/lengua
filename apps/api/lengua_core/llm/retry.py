"""Shared call-boundary helpers for the LLM providers (task 1.2.5).

Both the Groq and Gemini providers route their network calls through
:func:`call_with_retry`, which retries *transient* failures (HTTP 429 / 5xx and
connection blips) with exponential backoff. The clock is injected via ``sleep`` so
tests can patch it and never actually wait.

It also centralises the **request caps** every provider must honour at the call
boundary: a ceiling on vocabulary words per request (:func:`cap_words`) and the
per-operation ``max_output_tokens`` constants, so a single oversized request can
never run up latency or cost.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import TypeVar

T = TypeVar("T")

# ── Request caps (applied at the call boundary in every provider) ──────────────
#: Hard ceiling on vocabulary words accepted per generate/suggest request.
MAX_WORDS_PER_REQUEST = 30
#: ``max_output_tokens`` ceilings, sized per operation so an answer can't balloon.
GENERATE_MAX_TOKENS = 2048
SUGGEST_MAX_TOKENS = 512
EXPLAIN_MAX_TOKENS = 200

# ── Retry / backoff defaults ───────────────────────────────────────────────────
DEFAULT_MAX_ATTEMPTS = 3
DEFAULT_BASE_DELAY = 1.0


def cap_words(words: list[str]) -> list[str]:
    """Strip blanks and truncate ``words`` to :data:`MAX_WORDS_PER_REQUEST`.

    Applied before every request so an unbounded vocabulary list can't be sent to
    the model (cost + latency guard). Order is preserved.
    """
    cleaned = [w.strip() for w in words if w.strip()]
    return cleaned[:MAX_WORDS_PER_REQUEST]


def call_with_retry(
    fn: Callable[[], T],
    *,
    is_transient: Callable[[BaseException], bool],
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    base_delay: float = DEFAULT_BASE_DELAY,
    sleep: Callable[[float], None] = time.sleep,
) -> T:
    """Call ``fn`` with exponential backoff, retrying only transient errors.

    Up to ``max_attempts`` calls are made. Before each *retry* (never before the
    first attempt) it waits ``base_delay * 2 ** (n - 1)`` seconds via the injected
    ``sleep`` — patched in tests, so there is no real waiting. An error for which
    ``is_transient`` returns ``False`` propagates immediately; if every attempt
    raises a transient error, the last one is re-raised.
    """
    last_exc: Exception | None = None
    for attempt in range(max_attempts):
        if attempt:
            sleep(base_delay * 2 ** (attempt - 1))
        try:
            return fn()
        except Exception as exc:
            if not is_transient(exc):
                raise
            last_exc = exc
    # Reached only when every attempt raised a transient error (max_attempts >= 1).
    assert last_exc is not None
    raise last_exc
