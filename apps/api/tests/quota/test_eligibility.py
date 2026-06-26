"""Task 3.7.1 — the email-verified check is the FIRST gate.

An account whose email is not verified is refused at ``/generate`` with **403**
``{"code": "email_unverified"}`` before any rate limiter, counter, or provider is touched. The test
auth helper mints ``email_verified=True`` by default, so we explicitly authenticate as an
*unverified* account to exercise the block.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI

from app.deps import DEV_USER_ID
from lengua_core.llm.fake import FakeLLM
from tests.auth_helpers import authenticate_as
from tests.quota.conftest import client_for

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def test_unverified_blocked(quota_app: FastAPI) -> None:
    authenticate_as(quota_app, DEV_USER_ID, email_verified=False)
    FakeLLM.reset_call_count()

    async with client_for(quota_app) as client:
        # ``language_id`` is irrelevant — the email gate rejects before the route body (and thus the
        # language lookup and the provider) ever runs.
        resp = await client.post("/generate", json={"language_id": 1, "words": ["hola"]})

    assert resp.status_code == 403
    assert resp.json() == {"code": "email_unverified"}
    assert FakeLLM.call_count == 0  # no provider call happened
