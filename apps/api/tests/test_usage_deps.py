"""The privileged cost-guard session dependency ``app.deps.get_usage_db`` (group 3.1).

``get_usage_db`` yields a **dedicated**, RLS-*un*bound session (the connecting ``postgres``/owner
role) so the server can reach the global ``llm_budget`` kill-switch — ``REVOKE``\\d from the
``authenticated`` role and written only via ``SECURITY DEFINER`` functions. Two properties matter:

* the session is privileged (no bound RLS identity; can read ``llm_budget`` directly — a read the
  ``authenticated`` request session is denied, see ``tests/test_rls.py``); and
* within a request depending on **both** ``get_db`` and ``get_usage_db`` the two sessions are
  *distinct objects* — ``get_usage_db`` opens its own, so it is never the RLS-bound ``get_db``
  session (which would make the kill-switch RPCs run as ``authenticated`` → permission denied).
"""

from __future__ import annotations

import datetime

import pytest
from fastapi import Depends
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import UsageSession, dispose_engine
from app.deps import get_db, get_usage_db
from app.main import create_app
from app.repositories.usage import UsageRepository
from tests.auth_helpers import auth_header, install_test_auth
from tests.conftest import _skip_if_db_unreachable

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

# A far-future day with no budget row, so the read returns cleanly without touching real counters.
_DAY = datetime.date(2099, 9, 9)
_USER_ID = "12345678-1234-5678-1234-567812345678"


async def test_get_usage_db_yields_privileged_unbound_session() -> None:
    """The yielded session has no RLS identity and can read the server-only ``llm_budget``."""
    _skip_if_db_unreachable()
    gen = get_usage_db()
    session: UsageSession = await anext(gen)
    try:
        # Never RLS-bound (no stashed user id) → it runs as the privileged postgres role.
        assert "rls_user_id" not in session.info

        # Privileged: a direct read of the server-only kill-switch table succeeds here (the
        # authenticated request session gets permission denied — see tests/test_rls.py).
        await session.execute(text("SELECT count FROM llm_budget WHERE day = :d"), {"d": _DAY})

        # And the repository's privileged reader works through it.
        assert await UsageRepository(session).get_budget_count(_DAY) == 0
    finally:
        await gen.aclose()
        # Reset the process-wide engine the dependency created in this test's event loop, so a later
        # async test does not reuse a connection bound to a now-closed loop.
        await dispose_engine()


async def test_get_db_and_get_usage_db_are_distinct_sessions() -> None:
    """In a real request depending on both, the sessions differ; only ``get_db``'s is RLS-bound."""
    _skip_if_db_unreachable()
    app = create_app()
    install_test_auth(app)
    seen: dict[str, bool] = {}

    @app.get("/__sessions__")
    async def _sessions(
        db: AsyncSession = Depends(get_db),
        usage: UsageSession = Depends(get_usage_db),
    ) -> dict[str, bool]:
        seen["distinct"] = db is not usage
        seen["db_is_rls_bound"] = "rls_user_id" in db.info
        seen["usage_is_rls_bound"] = "rls_user_id" in usage.info
        return seen

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            resp = await client.get("/__sessions__", headers=auth_header(_USER_ID))
        assert resp.status_code == 200, resp.text
        assert seen["distinct"] is True, "get_db and get_usage_db must not share one session"
        assert seen["db_is_rls_bound"] is True, "get_db's session must be RLS-bound"
        assert seen["usage_is_rls_bound"] is False, "get_usage_db's session must stay unbound"
    finally:
        await dispose_engine()
