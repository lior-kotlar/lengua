"""Task 1.2.5 — the shared retry/backoff helper and the request caps.

Simulates two transient failures (e.g. 503) then success and asserts exactly three
attempts with exponential backoff — using a patched clock (an injected ``sleep``), so
there are no real sleeps. Also covers non-transient short-circuiting, exhaustion, and
the words-per-request cap.
"""

from __future__ import annotations

import pytest

from lengua_core.llm.retry import (
    MAX_WORDS_PER_REQUEST,
    call_with_retry,
    cap_words,
)

pytestmark = pytest.mark.disable_socket


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

    result = call_with_retry(flaky, is_transient=_is_transient, sleep=sleeps.append)

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


def test_exhausting_attempts_reraises_last_transient() -> None:
    attempts = 0
    sleeps: list[float] = []

    def always_busy() -> str:
        nonlocal attempts
        attempts += 1
        raise _Transient(f"503 #{attempts}")

    with pytest.raises(_Transient, match="#3"):
        call_with_retry(always_busy, is_transient=_is_transient, sleep=sleeps.append)
    assert attempts == 3
    assert sleeps == [1.0, 2.0]


def test_custom_attempts_and_base_delay() -> None:
    sleeps: list[float] = []

    def always_busy() -> str:
        raise _Transient("503")

    with pytest.raises(_Transient):
        call_with_retry(
            always_busy,
            is_transient=_is_transient,
            max_attempts=4,
            base_delay=0.5,
            sleep=sleeps.append,
        )
    assert sleeps == [0.5, 1.0, 2.0]  # 0.5 * 2**(n-1)


def test_cap_words_strips_and_truncates() -> None:
    assert cap_words(["  casa  ", "", "perro", "   "]) == ["casa", "perro"]
    many = [f"w{i}" for i in range(MAX_WORDS_PER_REQUEST + 10)]
    capped = cap_words(many)
    assert len(capped) == MAX_WORDS_PER_REQUEST
    assert capped[0] == "w0"
