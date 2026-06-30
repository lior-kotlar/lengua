"""Task 3.6.1 verify: ``/generate`` caps request size (422) and passes a max-tokens output cap.

Two cost-minimization guarantees on the generate path:

* **(a) Request-size cap.** An over-limit word list is **rejected with 422** at the API boundary —
  the :class:`~app.schemas.generate.GenerateRequest` schema caps ``words`` at
  ``MAX_WORDS_PER_REQUEST`` (env-overridable via settings), so an oversized request never reaches
  the provider. It is a hard reject, **not** the silent ``cap_words`` truncation the providers still
  apply defensively. The schema also enforces the lower bound — an empty ``words: []`` is likewise
  rejected with 422 (``minItems: 1``, S11) so a no-op generate never reaches the body to burn a
  daily count. Proven at the schema level (a ``pydantic.ValidationError``, which FastAPI renders as
  HTTP 422) and end-to-end over HTTP.
* **(b) Output-token cap.** Each allowed generate call passes the configured ``GENERATE_MAX_TOKENS``
  output cap to the vendor so an answer can't balloon in cost. Proven by driving the real
  :class:`~lengua_core.llm.groq.GroqProvider` with a recording fake vendor client and asserting it
  received ``max_tokens`` — i.e. the cap is observable at the vendor call.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from httpx import AsyncClient
from pydantic import ValidationError

from app.schemas.generate import GenerateRequest
from app.settings import get_settings
from lengua_core.llm.fake import FakeLLM
from lengua_core.llm.groq import GroqProvider
from lengua_core.llm.retry import GENERATE_MAX_TOKENS


class _RecordingGroqClient:
    """A stand-in for ``groq.Groq`` that records the kwargs of each chat-completion create call.

    Mirrors the real SDK call shape ``client.chat.completions.create(**kwargs)`` and returns a
    minimal response whose ``choices[0].message.content`` is a valid one-card JSON envelope, so the
    provider's parse step succeeds without any network.
    """

    def __init__(self, content: str) -> None:
        self.create_kwargs: list[dict[str, Any]] = []
        self._content = content
        self.chat = SimpleNamespace(completions=self)

    def create(self, **kwargs: Any) -> Any:
        self.create_kwargs.append(kwargs)
        message = SimpleNamespace(content=self._content)
        return SimpleNamespace(choices=[SimpleNamespace(message=message)])


def test_words_and_tokens_capped() -> None:
    """An over-limit word list is rejected (422), and the vendor call carries the max-tokens cap."""
    max_words = get_settings().max_words_per_request

    # (a) Over the cap → schema rejection (FastAPI renders this as HTTP 422). The boundary REJECTS,
    # it does not silently truncate. Exactly ``max_words`` is still accepted.
    over_limit = [f"w{i}" for i in range(max_words + 1)]
    with pytest.raises(ValidationError):
        GenerateRequest(language_id=1, words=over_limit)
    at_limit = [f"w{i}" for i in range(max_words)]
    assert len(GenerateRequest(language_id=1, words=at_limit).words) == max_words

    # (b) The configured output-token cap is passed to the vendor on the generate call.
    one_card_json = (
        '{"cards": [{"sentence": "Hola mundo.", "translation": "Hello world.", '
        '"used_words": ["hola"]}]}'
    )
    client = _RecordingGroqClient(one_card_json)
    provider = GroqProvider(api_key="test-key", model="llama-3.1-8b-instant", client=client)
    cards = provider.generate_cards(["hola"], "Spanish")

    assert len(cards) == 1
    assert client.create_kwargs, "the vendor client was never called"
    assert client.create_kwargs[0]["max_tokens"] == GENERATE_MAX_TOKENS


def test_empty_words_rejected_by_schema() -> None:
    """S11: an empty ``words`` list is a schema rejection (FastAPI → HTTP 422); one word passes."""
    with pytest.raises(ValidationError):
        GenerateRequest(language_id=1, words=[])
    # The lower bound is exactly one — a single word still validates.
    assert GenerateRequest(language_id=1, words=["hola"]).words == ["hola"]


@pytest.mark.integration
@pytest.mark.asyncio
async def test_over_limit_words_http_422(api_client: AsyncClient) -> None:
    """End-to-end: POST /generate with an over-limit word list → HTTP 422, no provider call."""
    lang = await api_client.post("/languages", json={"name": "Spanish", "code": "es"})
    language_id = int(lang.json()["id"])
    FakeLLM.reset_call_count()

    over_limit = [f"w{i}" for i in range(get_settings().max_words_per_request + 1)]
    resp = await api_client.post(
        "/generate", json={"language_id": language_id, "words": over_limit}
    )

    assert resp.status_code == 422
    assert FakeLLM.call_count == 0  # rejected at validation, before any provider call


@pytest.mark.integration
@pytest.mark.asyncio
async def test_empty_words_http_422(api_client: AsyncClient) -> None:
    """End-to-end: POST /generate with an empty word list → HTTP 422, no provider call (S11)."""
    lang = await api_client.post("/languages", json={"name": "Spanish", "code": "es"})
    language_id = int(lang.json()["id"])
    FakeLLM.reset_call_count()

    resp = await api_client.post("/generate", json={"language_id": language_id, "words": []})

    assert resp.status_code == 422
    assert FakeLLM.call_count == 0  # rejected at validation, before any provider call
