"""Demo/reviewer account seed (task 2.5.3).

The demo account (``scripts/seed_e2e.py``) provisions a pre-confirmed Supabase auth user with a
known password, a language, and LLM-free fixture cards including due ones — so an App Store / Play
reviewer can sign in and exercise the full review loop. These tests assert, against the live local
stack (``@pytest.mark.integration``, auto-skipped when unreachable):

* the demo auth user exists and is **email-verified** (admin-created users are pre-confirmed);
* the expected seeded rows are present (a language + ≥1 saved, due card);
* and end to end — **logging in** as the demo user (real password grant → a Supabase-signed JWT)
  and calling ``GET /review/due`` returns **≥1 due card**, with the deterministic FakeLLM and zero
  real LLM calls.
"""

from __future__ import annotations

import httpx
import psycopg
import pytest
from httpx import ASGITransport, AsyncClient

from app.db.session import dispose_engine
from app.deps import get_llm_provider
from app.main import create_app
from app.settings import Settings, get_settings
from lengua_core.llm.base import LLMProvider
from lengua_core.llm.fake import FakeLLM
from scripts.seed_e2e import DEMO_EMAIL, DEMO_LANGUAGE, DEMO_PASSWORD, SeedResult
from tests.conftest import database_url
from tests.supabase_auth import get_user, jwks_url, login

pytestmark = pytest.mark.integration


def test_demo_user_exists_and_is_email_verified(demo_account: SeedResult) -> None:
    """The demo auth user exists (correct email) and is confirmed (verified) so it can sign in."""
    with httpx.Client(timeout=30.0) as client:
        user = get_user(client, demo_account.user_id)
    assert user.get("email") == DEMO_EMAIL

    # Pre-confirmed via the Auth Admin API (email_confirm=true) → email_confirmed_at is set.
    with psycopg.connect(database_url()) as conn:
        row = conn.execute(
            "SELECT email_confirmed_at FROM auth.users WHERE id = %s", (demo_account.user_id,)
        ).fetchone()
    assert row is not None and row[0] is not None, "demo user must be email-verified"


def test_demo_seed_rows(demo_account: SeedResult) -> None:
    """The seed created the demo language and a non-empty set of saved, due cards."""
    with psycopg.connect(database_url()) as conn:
        language = conn.execute(
            "SELECT name FROM languages WHERE id = %s AND user_id = %s",
            (demo_account.language_id, demo_account.user_id),
        ).fetchone()
        assert language is not None and language[0] == DEMO_LANGUAGE

        due = conn.execute(
            "SELECT count(*) FROM cards WHERE user_id = %s AND saved = true AND due <= now()",
            (demo_account.user_id,),
        ).fetchone()
    assert due is not None and due[0] >= 1, "the demo deck must have at least one due card"


def _verify_real_supabase_token() -> Settings:
    """Settings that verify a *real* Supabase access token via JWKS (ES256 asymmetric keys)."""
    return Settings(  # type: ignore[call-arg]
        _env_file=None,
        supabase_jwt_secret="",
        supabase_jwks_url=jwks_url(),
    )


@pytest.mark.asyncio
async def test_demo_login_then_review_due_returns_due_card(demo_account: SeedResult) -> None:
    """Log in as the demo user (real JWT) and GET /review/due → ≥1 due card over the real stack."""
    # Real password-grant login → a Supabase-signed access token.
    with httpx.Client(timeout=30.0) as http:
        token = login(http, DEMO_EMAIL, DEMO_PASSWORD)
    assert token

    # Drive the app against the real DB (committed demo rows) with the real JWT verified. The
    # module-level engine is (re)bound to this test's event loop via dispose_engine().
    await dispose_engine()
    app = create_app()
    app.dependency_overrides[get_settings] = _verify_real_supabase_token

    def _fake_provider() -> LLMProvider:
        return FakeLLM()

    app.dependency_overrides[get_llm_provider] = _fake_provider
    FakeLLM.reset_call_count()
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            response = await client.get(
                "/review/due",
                params={"language_id": demo_account.language_id},
                headers={"Authorization": f"Bearer {token}"},
            )
        assert response.status_code == 200, response.text
        body = response.json()
        due_total = len(body["new"]) + len(body["due"])
        assert due_total >= 1, f"expected ≥1 due card for the demo reviewer, got {body}"
    finally:
        app.dependency_overrides.clear()
        await dispose_engine()

    # The review path touches no LLM; the demo cards are LLM-free fixtures (zero real LLM calls).
    assert FakeLLM.call_count == 0
