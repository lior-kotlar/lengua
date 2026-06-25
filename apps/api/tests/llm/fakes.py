"""Typed, network-free stand-ins for the Groq / Gemini SDK clients used in LLM tests.

These mimic only the tiny slice of each SDK the providers touch
(``client.chat.completions.create`` for Groq; ``client.models.generate_content`` for
Gemini), returning canned responses and recording a call count — so provider methods
can be exercised end-to-end without a network (the tests also run under
``pytest-socket --disable-socket``).
"""

from __future__ import annotations

from typing import Any

# ── Groq (OpenAI-compatible chat completions) ──────────────────────────────────


class _FakeMessage:
    def __init__(self, content: str) -> None:
        self.content = content


class _FakeChoice:
    def __init__(self, content: str) -> None:
        self.message = _FakeMessage(content)


class _FakeCompletion:
    def __init__(self, content: str) -> None:
        self.choices = [_FakeChoice(content)]


class FakeGroqCompletions:
    """Stands in for ``client.chat.completions``; returns canned content, counts calls."""

    def __init__(self, content: str) -> None:
        self._content = content
        self.calls = 0

    def create(self, **kwargs: Any) -> _FakeCompletion:
        self.calls += 1
        return _FakeCompletion(self._content)


class _FakeChat:
    def __init__(self, completions: FakeGroqCompletions) -> None:
        self.completions = completions


class FakeGroqClient:
    """Network-free stand-in for ``groq.Groq`` (exposes ``.chat.completions.create``)."""

    def __init__(self, content: str) -> None:
        self.completions = FakeGroqCompletions(content)
        self.chat = _FakeChat(self.completions)


# ── Gemini (google-genai) ──────────────────────────────────────────────────────


class FakeGenaiResponse:
    def __init__(self, *, parsed: Any = None, text: str | None = None) -> None:
        self.parsed = parsed
        self.text = text


class FakeGenaiModels:
    """Stands in for ``client.models``; returns a canned response, counts calls."""

    def __init__(self, response: FakeGenaiResponse) -> None:
        self._response = response
        self.calls = 0

    def generate_content(self, **kwargs: Any) -> FakeGenaiResponse:
        self.calls += 1
        return self._response


class FakeGenaiClient:
    """Network-free stand-in for ``genai.Client`` (exposes ``.models.generate_content``)."""

    def __init__(self, response: FakeGenaiResponse) -> None:
        self.models = FakeGenaiModels(response)
