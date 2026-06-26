"""Task 3.8.1 — the LLM token-usage reporting seam (offline, no network).

Covers the side-channel the per-call observability span reads ``llm.tokens_in/out`` from:

* :func:`capture_usage` / :func:`report_usage` — a provider reports usage into the active capture
  scope (and is a safe no-op outside one);
* :func:`report_groq_usage` / :func:`report_gemini_usage` — adapting each vendor response shape,
  including missing usage and non-numeric / negative token fields (coerced to 0).
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from lengua_core.llm.usage import (
    TokenUsage,
    capture_usage,
    report_gemini_usage,
    report_groq_usage,
    report_usage,
)

pytestmark = pytest.mark.disable_socket


def test_capture_usage_records_reported_counts() -> None:
    with capture_usage() as usage:
        report_usage(11, 7)
    assert usage == TokenUsage(tokens_in=11, tokens_out=7)


def test_report_usage_is_noop_without_capture_scope() -> None:
    # No active scope → reporting is a safe no-op (a provider called directly in a unit test).
    report_usage(5, 5)  # must not raise


def test_nested_capture_scopes_are_isolated() -> None:
    with capture_usage() as outer:
        report_usage(1, 1)
        with capture_usage() as inner:
            report_usage(2, 3)
        assert inner == TokenUsage(tokens_in=2, tokens_out=3)
        # The inner scope is popped on exit, so the outer sink is restored and untouched by it.
        report_usage(4, 5)
    assert outer == TokenUsage(tokens_in=4, tokens_out=5)


def test_report_groq_usage_reads_response_usage() -> None:
    response = SimpleNamespace(usage=SimpleNamespace(prompt_tokens=31, completion_tokens=12))
    with capture_usage() as usage:
        report_groq_usage(response)
    assert usage == TokenUsage(tokens_in=31, tokens_out=12)


def test_report_groq_usage_handles_missing_usage() -> None:
    with capture_usage() as usage:
        report_groq_usage(SimpleNamespace())  # no ``usage`` attribute at all
    assert usage == TokenUsage(tokens_in=0, tokens_out=0)


def test_report_gemini_usage_reads_usage_metadata() -> None:
    response = SimpleNamespace(
        usage_metadata=SimpleNamespace(prompt_token_count=20, candidates_token_count=9)
    )
    with capture_usage() as usage:
        report_gemini_usage(response)
    assert usage == TokenUsage(tokens_in=20, tokens_out=9)


def test_report_gemini_usage_coerces_missing_and_invalid_fields() -> None:
    # A None candidate count + a negative prompt count both coerce to 0 (no crash, never negative).
    response = SimpleNamespace(
        usage_metadata=SimpleNamespace(prompt_token_count=-3, candidates_token_count=None)
    )
    with capture_usage() as usage:
        report_gemini_usage(response)
    assert usage == TokenUsage(tokens_in=0, tokens_out=0)


def test_report_gemini_usage_handles_missing_metadata() -> None:
    with capture_usage() as usage:
        report_gemini_usage(SimpleNamespace())  # no ``usage_metadata``
    assert usage == TokenUsage(tokens_in=0, tokens_out=0)
