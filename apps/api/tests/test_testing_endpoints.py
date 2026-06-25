"""Tests for the test-only LLM router and its provider gating (tasks 0.4.2 / 0.5.6).

These cover :mod:`app.testing` and the ``LLM_PROVIDER=fake`` gate in :func:`app.main.create_app`
that the E2E job relies on. The *no-network* guarantee of the FakeLLM these endpoints call is
proven separately and directly in ``test_fake_llm.py`` (``disable_socket``); here we use the
in-process Starlette ``TestClient`` (which needs the loopback transport) to assert the HTTP
wiring — provider gating, the call counter, and deterministic generation over HTTP.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from lengua_core.llm.fake import FakeLLM


def _fake_client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """A TestClient for an app built with ``LLM_PROVIDER=fake`` (test router mounted)."""
    monkeypatch.setenv("LLM_PROVIDER", "fake")
    return TestClient(create_app())


def test_test_router_absent_for_real_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    """With a real provider the test-only routes are not mounted (404)."""
    monkeypatch.setenv("LLM_PROVIDER", "groq")
    client = TestClient(create_app())
    assert client.get("/__test__/llm-calls").status_code == 404
    assert client.post("/__test__/generate", json={}).status_code == 404
    # Health is always present regardless of provider.
    assert client.get("/health").status_code == 200


def test_test_router_defaults_to_groq_when_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    """Unset LLM_PROVIDER defaults to groq, so the test router is absent."""
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    client = TestClient(create_app())
    assert client.get("/__test__/llm-calls").status_code == 404


def test_llm_calls_counter_starts_and_increments(monkeypatch: pytest.MonkeyPatch) -> None:
    """The counter is exposed and increments exactly once per generate call."""
    client = _fake_client(monkeypatch)
    FakeLLM.reset_call_count()

    before = client.get("/__test__/llm-calls")
    assert before.status_code == 200
    assert before.json() == {"calls": 0}

    gen = client.post("/__test__/generate", json={"words": ["casa"], "language": "Spanish"})
    assert gen.status_code == 200

    after = client.get("/__test__/llm-calls")
    assert after.json() == {"calls": 1}


def test_generate_returns_deterministic_fake_cards(monkeypatch: pytest.MonkeyPatch) -> None:
    """The HTTP generate probe returns the deterministic FakeLLM output."""
    client = _fake_client(monkeypatch)
    FakeLLM.reset_call_count()

    resp = client.post(
        "/__test__/generate",
        json={"words": ["casa", "perro"], "language": "Spanish", "level_band": "A2"},
    )
    assert resp.status_code == 200
    cards = resp.json()
    assert [c["used_words"][0] for c in cards] == ["casa", "perro"]
    assert all("A2" in c["sentence"] for c in cards)
    # Same request again → identical payload (determinism over HTTP).
    again = client.post(
        "/__test__/generate",
        json={"words": ["casa", "perro"], "language": "Spanish", "level_band": "A2"},
    )
    assert again.json() == cards


def test_generate_uses_request_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    """An empty body falls back to the documented defaults (one 'casa' card)."""
    client = _fake_client(monkeypatch)
    resp = client.post("/__test__/generate", json={})
    assert resp.status_code == 200
    cards = resp.json()
    assert len(cards) == 1
    assert cards[0]["used_words"] == ["casa"]
