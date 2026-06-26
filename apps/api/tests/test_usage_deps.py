"""The privileged cost-guard session dependency ``app.deps.get_usage_db`` (group 3.1).

``get_usage_db`` deliberately yields an RLS-*un*bound session (the connecting ``postgres``/owner
role) so the server can reach the global ``llm_budget`` kill-switch — which is ``REVOKE``\\d from
the ``authenticated`` role and written only via ``SECURITY DEFINER`` functions. This proves the
session it hands back is privileged: it carries no bound RLS identity and can read ``llm_budget``
directly (a read the ``authenticated`` request session is denied — see ``tests/test_rls.py``).
"""

from __future__ import annotations

import datetime

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.session import async_dsn
from app.deps import get_usage_db
from app.repositories.usage import UsageRepository
from tests.conftest import _skip_if_db_unreachable, database_url

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

# A far-future day with no budget row, so the read returns cleanly without touching real counters.
_DAY = datetime.date(2099, 9, 9)


async def test_get_usage_db_yields_privileged_unbound_session() -> None:
    """The returned session is the same one, has no RLS identity, and can read ``llm_budget``."""
    _skip_if_db_unreachable()
    engine = create_async_engine(async_dsn(database_url()))
    sessionmaker = async_sessionmaker(bind=engine, expire_on_commit=False)
    try:
        async with sessionmaker() as session:
            returned = await get_usage_db(session)
            # It hands back the very session it was given, never RLS-bound (no stashed user id).
            assert returned is session
            assert "rls_user_id" not in session.info

            # Privileged: a direct read of the server-only kill-switch table succeeds here (the
            # authenticated request session gets permission denied — see tests/test_rls.py).
            await session.execute(text("SELECT count FROM llm_budget WHERE day = :d"), {"d": _DAY})

            # And the repository's privileged reader works through it.
            assert await UsageRepository(session).get_budget_count(_DAY) == 0
    finally:
        await engine.dispose()
