"""Shared call-boundary helpers for the LLM providers (tasks 1.2.5 / 3.5.2).

Both the Groq and Gemini providers route their network calls through
:func:`call_with_retry`, which retries *transient* failures (HTTP 429 / 5xx and
connection blips) with **exponential backoff + jitter**. The clock is injected via
``sleep`` and the jitter source via ``rng`` so tests can patch both and never actually
wait (and reproduce exact delays). When transient errors *persist* across every attempt
the helper raises a clean, provider-agnostic :class:`LLMTransientError` (the raw provider
429/5xx attached as ``__cause__``) so the app layer can map it to a friendly busy
response instead of letting a vendor exception surface as an unhandled 500 (task 3.5.2).

It also centralises the **request caps** every provider must honour at the call
boundary: a ceiling on vocabulary words per request (:func:`cap_words`) and the
per-operation ``max_output_tokens`` constants, so a single oversized request can
never run up latency or cost.
"""

from __future__ import annotations

import random
import time
from collections.abc import Callable
from typing import TypeVar

T = TypeVar("T")


class LLMTransientError(Exception):
    """Raised when transient provider errors (429 / 5xx / timeouts) persist across all retries.

    The clean, provider-agnostic signal that the LLM backend is *temporarily* unavailable. The
    original vendor exception is attached both as :attr:`original` and as the exception ``__cause__``
    (``raise ... from``), so logging/observability keep the underlying status. The app layer maps
    this to a friendly **503 ``server_busy``** response (see ``app.llm_runner``) rather than letting
    a raw provider 429/5xx escape as an unhandled 500.
    """

    def __init__(self, original: BaseException) -> None:
        self.original = original
        super().__init__(f"LLM provider call failed after retries: {original!r}")

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
    rng: Callable[[], float] = random.random,
) -> T:
    """Call ``fn`` with exponential backoff + jitter, retrying only transient errors.

    Up to ``max_attempts`` calls are made. Before each *retry* (never before the first attempt) it
    waits using **full jitter**: ``base_delay * 2 ** (n - 1) * rng()`` seconds, where ``rng()`` is a
    value in ``[0, 1)``. Jitter spreads concurrent clients' retries so they don't synchronise into a
    thundering herd against the provider's rate limit. Both the clock (``sleep``) and the jitter
    source (``rng``) are injected so tests fake them and assert exact delays (a fake ``rng`` returning
    ``1.0`` reproduces the un-jittered exponential ``base_delay * 2 ** (n - 1)``).

    An error for which ``is_transient`` returns ``False`` propagates immediately (a real client/parse
    bug must not be masked). If **every** attempt raises a *transient* error, the retries are
    considered exhausted and a :class:`LLMTransientError` is raised (with the last vendor exception as
    its ``__cause__``) — the clean signal the app layer renders as a friendly 503 ``server_busy``
    rather than an unhandled 500.
    """
    last_exc: BaseException | None = None
    for attempt in range(max_attempts):
        if attempt:
            backoff = base_delay * 2 ** (attempt - 1)
            sleep(backoff * rng())
        try:
            return fn()
        except Exception as exc:
            if not is_transient(exc):
                raise
            last_exc = exc
    # Reached only when every attempt raised a transient error (max_attempts >= 1).
    assert last_exc is not None
    raise LLMTransientError(last_exc) from last_exc
