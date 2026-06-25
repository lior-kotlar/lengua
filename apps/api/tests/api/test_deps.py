"""Unit tests for the request dependencies (task 1.5.1) — no DB required.

Guards the invariant that the placeholder ``current_user`` matches the seeded dev user and the
factory default, so FK-bound inserts in the API tests resolve, and that ``get_llm_provider``
honors ``LLM_PROVIDER``.
"""

from __future__ import annotations

import pytest

from app import deps
from lengua_core.llm.fake import FakeLLM
from scripts import seed_dev_user
from tests import factories


@pytest.mark.asyncio
async def test_current_user_returns_dev_uuid() -> None:
    assert await deps.current_user() == deps.DEV_USER_ID


def test_dev_user_id_matches_seed_and_factory() -> None:
    # current_user must equal the seeded profile + factory default so FK inserts line up.
    assert str(deps.DEV_USER_ID) == seed_dev_user.DEV_USER_ID
    assert str(deps.DEV_USER_ID) == factories.DEMO_USER_ID


def test_get_llm_provider_honors_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "fake")
    assert isinstance(deps.get_llm_provider(), FakeLLM)
