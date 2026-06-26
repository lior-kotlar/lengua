"""Shared pytest fixtures, including the Supabase-CLI test-Postgres wiring (task 0.4.3).

Isolation strategy (per the test-infra design):

- **Module-scoped clean DB** — :func:`clean_db` opens one autocommit connection per test module
  and ``TRUNCATE … RESTART IDENTITY CASCADE`` of the 8 app tables, giving each module a known
  empty starting point (and resetting identity sequences so ids are predictable).
- **Per-test SAVEPOINT rollback** — :func:`db` hands each test a connection inside a transaction
  with a ``SAVEPOINT``; whatever the test writes is rolled back at teardown, so tests in a
  module don't see each other's rows. Fast, and no re-truncation between tests.
- **Offline-safe** — DB tests are marked ``@pytest.mark.integration``; the autouse
  :func:`_skip_integration_without_db` fixture ``pytest.skip``s them when ``DATABASE_URL`` can't
  be reached, so the plain unit suite still passes with no Postgres running.

``DATABASE_URL`` defaults to the local Supabase CLI Postgres (``…@127.0.0.1:54322/postgres``).
"""

from __future__ import annotations

import functools
import os
import shutil
import subprocess
from collections.abc import AsyncIterator, Iterator
from typing import TYPE_CHECKING

import psycopg
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.db.session import async_dsn
from scripts.seed_e2e import SeedResult, seed

if TYPE_CHECKING:
    from httpx import AsyncClient

# Map ``supabase status -o env`` keys → the env vars our seed/DB code reads. Auto-sourced once
# at import so the literal verify (``uv run pytest tests/test_seed.py``) works against a running
# local stack without the caller exporting anything; explicit env always wins.
_SUPABASE_ENV_MAP = {
    "API_URL": "SUPABASE_URL",
    "SERVICE_ROLE_KEY": "SUPABASE_SERVICE_ROLE_KEY",
    "DB_URL": "DATABASE_URL",
}


def _source_supabase_env() -> None:
    """Best-effort: fill missing Supabase env vars from ``supabase status -o env``.

    No-op when the CLI isn't on PATH or the stack isn't running — the integration tests then
    simply skip (DB unreachable), keeping the unit suite green offline.
    """
    if all(os.getenv(v) for v in _SUPABASE_ENV_MAP.values()):
        return
    if shutil.which("supabase") is None:
        return
    try:
        out = subprocess.run(
            ["supabase", "status", "-o", "env"],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return
    for line in out.splitlines():
        key, sep, value = line.partition("=")
        if not sep or key.strip() not in _SUPABASE_ENV_MAP:
            continue
        target = _SUPABASE_ENV_MAP[key.strip()]
        if not os.getenv(target):  # never override an explicit value
            os.environ[target] = value.strip().strip('"')


_source_supabase_env()

# The 8 application tables from the initial migration, child-before-parent so an explicit
# order would work; CASCADE makes order moot but we keep it tidy. ``llm_budget`` is global.
APP_TABLES = (
    "reviews",
    "cards",
    "proficiency",
    "user_settings",
    "llm_usage",
    "languages",
    "profiles",
    "llm_budget",
)

# Local Supabase CLI default DSN (postgres superuser, port 54322).
DEFAULT_DATABASE_URL = "postgresql://postgres:postgres@127.0.0.1:54322/postgres"


def database_url() -> str:
    """The test database DSN (``DATABASE_URL`` env, else the local Supabase default)."""
    return os.getenv("DATABASE_URL") or DEFAULT_DATABASE_URL


@functools.cache
def _db_reachable() -> bool:
    """True if a short-timeout connection to :func:`database_url` succeeds.

    Cached for the session so we pay the connect probe once, not once per integration test
    (a 2s timeout per test adds up when no DB is running).
    """
    try:
        with psycopg.connect(database_url(), connect_timeout=2) as conn:
            conn.execute("SELECT 1")
        return True
    except Exception:
        return False


def _skip_if_db_unreachable() -> None:
    """``pytest.skip`` (not error) when the test DB can't be reached.

    Called both from the autouse guard (for marker-only tests) and from the DB fixtures
    themselves, so a missing Postgres yields a *skip* even though the connection attempt lives
    inside fixture setup (where a raised exception would otherwise surface as an ERROR).
    """
    if not _db_reachable():
        pytest.skip(f"DATABASE_URL unreachable ({database_url()}); skipping integration test")


@pytest.fixture(autouse=True)
def _skip_integration_without_db(request: pytest.FixtureRequest) -> None:
    """Skip any ``@pytest.mark.integration`` test when the database is unreachable.

    Keeps the unit suite green offline (no Docker/Supabase) while still running DB tests in CI
    and locally once ``supabase start`` is up.
    """
    if request.node.get_closest_marker("integration"):
        _skip_if_db_unreachable()


@pytest.fixture(scope="module")
def clean_db() -> Iterator[None]:
    """Module-scoped: truncate the app tables once so the module starts from an empty DB."""
    # Belt-and-suspenders: skip here too, so an unreachable DB during *fixture setup* surfaces
    # as a skip rather than a connection-timeout ERROR (fixture/autouse ordering is not
    # guaranteed across scopes).
    _skip_if_db_unreachable()
    with psycopg.connect(database_url(), autocommit=True) as conn:
        conn.execute(f"TRUNCATE {', '.join(APP_TABLES)} RESTART IDENTITY CASCADE")
        yield


@pytest.fixture
def demo_account() -> SeedResult:
    """Seed the deterministic demo/reviewer account and return the :class:`SeedResult`.

    Wraps :func:`scripts.seed_e2e.seed` (Auth-Admin create → trigger makes the profile → insert
    a language + due cards). Idempotent, so it's safe whether or not the account already exists.
    Used by ``test_seed.py`` and available to any future E2E/integration test (and reused for
    store-review later). Skips when the DB/Auth stack is unreachable.
    """
    _skip_if_db_unreachable()
    return seed()


@pytest.fixture
def db(clean_db: None) -> Iterator[psycopg.Connection]:
    """Per-test connection wrapped in a transaction + SAVEPOINT that is rolled back at teardown.

    Depends on :func:`clean_db` so the module is truncated before the first test. Each test sees
    a connection where its writes are isolated and automatically undone, so tests within a
    module don't leak rows into one another.
    """
    conn = psycopg.connect(database_url())
    try:
        # Open an outer transaction and a savepoint; rolling back to the savepoint undoes the
        # test's writes without ending the connection.
        conn.execute("BEGIN")
        conn.execute("SAVEPOINT test_savepoint")
        yield conn
        conn.execute("ROLLBACK TO SAVEPOINT test_savepoint")
        conn.rollback()
    finally:
        conn.close()


@pytest_asyncio.fixture
async def db_session(clean_db: None) -> AsyncIterator[AsyncSession]:
    """Per-test async :class:`AsyncSession` whose writes are rolled back at teardown.

    The async analogue of :func:`db` (used by the SQLAlchemy repository/service tests in groups
    1.3b/1.5, and by ``tests/db/test_session.py``): it opens a connection, begins an outer
    transaction, and binds an ``AsyncSession`` with ``join_transaction_mode="create_savepoint"``
    so that even code under test which calls ``commit()`` only releases a SAVEPOINT — the outer
    transaction is rolled back at teardown, isolating each test. Depends on :func:`clean_db` so
    the module starts from a truncated DB with predictable identity ids (and so an unreachable
    database surfaces as a skip rather than an error). A fresh engine is created per test and
    disposed at teardown, keeping every connection bound to the test's own event loop.
    """
    engine = create_async_engine(async_dsn(database_url()))
    conn = await engine.connect()
    trans = await conn.begin()
    session = AsyncSession(
        bind=conn,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    try:
        yield session
    finally:
        await session.close()
        if trans.is_active:
            await trans.rollback()
        await conn.close()
        await engine.dispose()


@pytest_asyncio.fixture
async def multiuser_client(db_session: AsyncSession) -> AsyncIterator[AsyncClient]:
    """An ASGI client that verifies **real** test JWTs, so one test can act as multiple users.

    Unlike ``tests/api/conftest.py``'s ``api_client`` (which pins a single authenticated identity
    via a dependency override), this leaves the real ``current_user`` verification in place and only
    points it at the test JWT secret (:func:`tests.auth_helpers.install_test_auth`). Each request
    then carries its own ``auth_header(<user_id>)`` token, so a single test can drive both user A
    and user B and prove cross-tenant isolation at the HTTP layer.

    The DB dependency is the test's rolled-back :func:`db_session` (shared so the test can both act
    through the API and assert on the same session) and the LLM is the deterministic ``FakeLLM``.
    User A's profile (the seeded ``DEV_USER_ID``) is provisioned so A's FK-bound inserts resolve;
    user B is a token-only identity that owns no rows.
    """
    from httpx import ASGITransport, AsyncClient

    from app.db.session import UsageSession
    from app.deps import get_db, get_llm_provider, get_usage_db
    from app.llm_runner import LLMConcurrencyLimiter, get_llm_limiter
    from app.main import create_app
    from app.ratelimit import InProcessRateLimiter, RateLimiter, get_rate_limiter
    from lengua_core.llm.base import LLMProvider
    from lengua_core.llm.fake import FakeLLM
    from scripts.seed_dev_user import seed_dev_user
    from tests.auth_helpers import install_test_auth

    _skip_if_db_unreachable()
    seed_dev_user()  # committed profile for user A (DEV_USER_ID) so its inserts resolve

    app = create_app()

    async def _override_get_db() -> AsyncIterator[AsyncSession]:
        yield db_session  # do not close — the test still queries this session afterwards

    async def _override_get_usage_db() -> AsyncIterator[UsageSession]:
        # Share the test's rolled-back ``db_session`` for the cost-guard usage session (Phase 3.2)
        # so on-success increments stay in the test transaction and can see uncommitted rows such as
        # a token-only user's profile (see ``tests/api/conftest.py`` for the full rationale).
        yield UsageSession(db_session)

    def _override_provider() -> LLMProvider:
        return FakeLLM()

    # Fresh, effectively-unlimited per-user rate limiter (Phase 3.3) so cross-tenant assertions
    # aren't perturbed by the per-minute ceiling and no global window bleeds across tests.
    test_rate_limiter = InProcessRateLimiter(limit=1_000_000)

    def _override_rate_limiter() -> RateLimiter:
        return test_rate_limiter

    # Fresh, generous concurrency limiter (3.5) so the process-wide singleton never spans loops.
    test_llm_limiter = LLMConcurrencyLimiter(max_concurrency=4)

    def _override_llm_limiter() -> LLMConcurrencyLimiter:
        return test_llm_limiter

    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_usage_db] = _override_get_usage_db
    app.dependency_overrides[get_llm_provider] = _override_provider
    app.dependency_overrides[get_rate_limiter] = _override_rate_limiter
    app.dependency_overrides[get_llm_limiter] = _override_llm_limiter
    install_test_auth(app)  # verify real bearer tokens against the test secret
    FakeLLM.reset_call_count()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client
    app.dependency_overrides.clear()
