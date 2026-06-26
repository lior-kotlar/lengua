"""Tasks 1.2.5 / 3.5.2 — the shared retry/backoff helper, jitter, and the request caps.

Simulates transient failures then success and asserts exactly the right number of attempts with
exponential backoff — using a patched clock (an injected ``sleep``) and a patched jitter source (an
injected ``rng``), so there are no real sleeps and the delays are exact. A fake ``rng`` returning
``1.0`` reproduces the un-jittered exponential ``base_delay * 2 ** (n - 1)``. Also covers
non-transient short-circuiting, the friendly :class:`LLMTransientError` on exhaustion (3.5.2), and
the words-per-request cap.
"""

from __future__ import annotations

import pytest

from lengua_core.llm.retry import (
    MAX_WORDS_PER_REQUEST,
    LLMTransientError,
    call_with_retry,
    cap_words,
)

pytestmark = pytest.mark.disable_socket

#: A fake jitter source pinned to its maximum (``1.0``) so ``backoff * rng()`` == the full backoff,
#: letting these tests assert exact, un-jittered delays.
_NO_JITTER = 1.0


class _Transient(Exception):
    """An error the predicate below treats as retryable."""


class _Fatal(Exception):
    """An error the predicate below treats as non-retryable."""


def _is_transient(exc: BaseException) -> bool:
    return isinstance(exc, _Transient)


def test_two_failures_then_success_makes_exactly_three_attempts() -> None:
    attempts = 0
    sleeps: list[float] = []

    def flaky() -> str:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise _Transient(f"503 #{attempts}")
        return "ok"

    result = call_with_retry(
        flaky, is_transient=_is_transient, sleep=sleeps.append, rng=lambda: _NO_JITTER
    )

    assert result == "ok"
    assert attempts == 3  # two failures + one success
    assert sleeps == [1.0, 2.0]  # exponential backoff, no real sleeping


def test_success_on_first_try_does_not_sleep() -> None:
    sleeps: list[float] = []
    result = call_with_retry(lambda: 42, is_transient=_is_transient, sleep=sleeps.append)
    assert result == 42
    assert sleeps == []


def test_non_transient_error_propagates_immediately() -> None:
    attempts = 0
    sleeps: list[float] = []

    def boom() -> str:
        nonlocal attempts
        attempts += 1
        raise _Fatal("400")

    with pytest.raises(_Fatal):
        call_with_retry(boom, is_transient=_is_transient, sleep=sleeps.append)
    assert attempts == 1  # not retried
    assert sleeps == []


def test_exhausting_attempts_raises_llm_transient_error() -> None:
    attempts = 0
    sleeps: list[float] = []

    def always_busy() -> str:
        nonlocal attempts
        attempts += 1
        raise _Transient(f"503 #{attempts}")

    with pytest.raises(LLMTransientError) as exc_info:
        call_with_retry(
            always_busy, is_transient=_is_transient, sleep=sleeps.append, rng=lambda: _NO_JITTER
        )
    assert attempts == 3
    assert sleeps == [1.0, 2.0]
    # The original vendor error is preserved on the typed error and as its ``__cause__``.
    assert isinstance(exc_info.value.original, _Transient)
    assert "#3" in str(exc_info.value.original)
    assert isinstance(exc_info.value.__cause__, _Transient)


def test_custom_attempts_and_base_delay() -> None:
    sleeps: list[float] = []

    def always_busy() -> str:
        raise _Transient("503")

    with pytest.raises(LLMTransientError):
        call_with_retry(
            always_busy,
            is_transient=_is_transient,
            max_attempts=4,
            base_delay=0.5,
            sleep=sleeps.append,
            rng=lambda: _NO_JITTER,
        )
    assert sleeps == [0.5, 1.0, 2.0]  # 0.5 * 2**(n-1)


def test_jitter_scales_backoff_by_rng() -> None:
    """``rng()`` in ``[0, 1)`` scales each delay (full jitter): a fixed 0.5 halves the backoff."""
    sleeps: list[float] = []

    def always_busy() -> str:
        raise _Transient("503")

    with pytest.raises(LLMTransientError):
        call_with_retry(
            always_busy, is_transient=_is_transient, sleep=sleeps.append, rng=lambda: 0.5
        )
    assert sleeps == [0.5, 1.0]  # 0.5 * [1.0, 2.0]


def test_cap_words_strips_and_truncates() -> None:
    assert cap_words(["  casa  ", "", "perro", "   "]) == ["casa", "perro"]
    many = [f"w{i}" for i in range(MAX_WORDS_PER_REQUEST + 10)]
    capped = cap_words(many)
    assert len(capped) == MAX_WORDS_PER_REQUEST
    assert capped[0] == "w0"
