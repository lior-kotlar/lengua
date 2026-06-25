"""Task 1.2.5 — each provider classifies which errors are worth retrying.

The shared backoff helper (see ``test_retry.py``) decides *how* to retry; these tests
pin *what* counts as transient for each provider: HTTP 429 / 5xx and connection/timeout
blips retry, while a 4xx like 400 propagates immediately. No network (``disable_socket``).
"""

from __future__ import annotations

import groq
import httpx
import pytest
from google.genai import errors

from lengua_core.llm.gemini import _is_transient as gemini_is_transient
from lengua_core.llm.groq import _is_transient as groq_is_transient

pytestmark = pytest.mark.disable_socket


class _StatusError(Exception):
    """A minimal stand-in for an SDK status error carrying ``status_code``/``code``."""

    def __init__(self, status_code: int) -> None:
        super().__init__(f"status {status_code}")
        self.status_code = status_code
        self.code = status_code


@pytest.mark.parametrize("status", [429, 500, 502, 503, 504])
def test_groq_retries_transient_statuses(status: int) -> None:
    assert groq_is_transient(_StatusError(status)) is True


def test_groq_retries_connection_and_timeout_errors() -> None:
    request = httpx.Request("POST", "https://api.groq.com")
    assert groq_is_transient(groq.APIConnectionError(request=request)) is True
    assert groq_is_transient(groq.APITimeoutError(request=request)) is True


@pytest.mark.parametrize("status", [400, 401, 404, 422])
def test_groq_does_not_retry_client_errors(status: int) -> None:
    assert groq_is_transient(_StatusError(status)) is False


def test_groq_does_not_retry_plain_exception() -> None:
    assert groq_is_transient(ValueError("boom")) is False


def test_gemini_retries_server_errors() -> None:
    server_error = errors.ServerError(503, {"error": {"code": 503, "message": "busy"}})
    assert gemini_is_transient(server_error) is True


def test_gemini_retries_rate_limit_but_not_other_client_errors() -> None:
    rate_limited = errors.ClientError(429, {"error": {"code": 429, "message": "rate"}})
    bad_request = errors.ClientError(400, {"error": {"code": 400, "message": "bad"}})
    assert gemini_is_transient(rate_limited) is True
    assert gemini_is_transient(bad_request) is False


def test_gemini_does_not_retry_plain_exception() -> None:
    assert gemini_is_transient(ValueError("boom")) is False
