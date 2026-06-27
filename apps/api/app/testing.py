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

from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.auth import CurrentUser
from app.deps import get_current_user
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


@router.get("/debug-error")
def debug_error(_user: Annotated[CurrentUser, Depends(get_current_user)]) -> None:
    """Deliberately raise so the Sentry capture path can be verified (task 5.4.1).

    Like the rest of this router it is mounted **only** under ``LLM_PROVIDER=fake`` (see
    :func:`app.main.create_app`), so it can NEVER be reached in dev/staging/prod. It additionally
    requires a valid bearer token: an anonymous caller gets ``401`` (the route is unreachable and
    leaks nothing), and an authenticated caller's id is bound onto Sentry's scope by
    :func:`app.deps.get_current_user` before this raises — so the captured Sentry event carries the
    ``user_id`` + the active ``trace_id``. The raised error surfaces as a generic ``500`` with no
    internal detail in the response body.
    """
    raise RuntimeError("Intentional test-only error for Sentry verification.")


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
