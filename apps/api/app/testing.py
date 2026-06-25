"""Test-only HTTP surface for the E2E zero-LLM-call assertion (tasks 0.4.2 / 0.5.6).

This router is mounted **only** when ``LLM_PROVIDER=fake`` (see :func:`app.main.create_app`), so
it never exists in a dev/staging/prod build. It exists purely so the Playwright E2E suite can
drive the LLM seam over HTTP against the ephemeral stack and prove that:

1. the app actually calls the configured provider (the :class:`~lengua_core.llm.fake.FakeLLM`
   call counter increments when ``POST /__test__/generate`` is hit), and
2. it makes **zero real LLM network calls** — the provider is the deterministic ``FakeLLM``
   (which does no I/O; unit-proven with ``pytest-socket``) and the container runs with **no**
   Groq/Gemini API keys, so a real call is impossible.

The full Phase 1 generate/save/review HTTP API is unrelated to this and replaces nothing here.
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field

from lengua_core.llm import get_provider
from lengua_core.llm.fake import FakeLLM
from lengua_core.models import GeneratedCard

router = APIRouter(prefix="/__test__", tags=["test-only"])


class GenerateRequest(BaseModel):
    """Inputs for the test-only generation probe."""

    words: list[str] = Field(default_factory=lambda: ["casa"])
    language: str = "Spanish"
    level_band: str | None = None


class LlmCallsResponse(BaseModel):
    """The process-wide FakeLLM call counter — asserted by the E2E to be 0 then >0."""

    calls: int


@router.get("/llm-calls", response_model=LlmCallsResponse)
def llm_calls() -> LlmCallsResponse:
    """Return how many times the (fake) LLM provider has been invoked this process."""
    return LlmCallsResponse(calls=FakeLLM.call_count)


@router.post("/generate", response_model=list[GeneratedCard])
def generate(body: GenerateRequest) -> list[GeneratedCard]:
    """Exercise the LLM seam over HTTP and return the generated cards.

    Uses :func:`lengua_core.llm.get_provider` exactly as the real generate flow will, so hitting
    this endpoint increments :attr:`FakeLLM.call_count`. With ``LLM_PROVIDER=fake`` the result is
    deterministic and no network call is made.
    """
    provider = get_provider()
    cards: list[GeneratedCard] = provider.generate_cards(
        words=body.words, language=body.language, level_band=body.level_band
    )
    return cards
