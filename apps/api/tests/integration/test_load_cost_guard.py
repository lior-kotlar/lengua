"""Phase 3 EXIT GATE — the zero-paid-usage load test (the headline "never get a bill" proof).

Drives sustained traffic at the real router → guard → repository → cost-guard stack with the
deterministic ``FakeLLM`` (``LLM_PROVIDER`` faked; **zero** real LLM calls, zero network) and proves
every cost-guard invariant holds under load:

* :func:`test_sustained_concurrent_load_holds_global_killswitch` — the headline. Genuinely
  **concurrent** ``POST /generate`` across **multiple** users (``asyncio.gather``): a first wave of
  exactly ``GLOBAL_DAILY_BUDGET`` requests all succeed (spending the budget), then a second wave
  across all users is refused **every** time with ``daily_limit_reached`` — the global kill-switch
  trips project-wide. ``FakeLLM.call_count == GLOBAL_DAILY_BUDGET`` (≤ the ceiling), so the real
  operator key is invoked at most budget times and no real provider is ever constructed.
* :func:`test_per_user_daily_cap_never_exceeded_under_burst` — a single user's burst never exceeds
  its per-user daily cap; over-cap requests get **429** ``daily_cap_reached`` and the counter stops
  at the cap.
* :func:`test_rate_limit_holds_under_burst` — a burst inside one window is rate-limited past the
  per-user ceiling (**429** ``rate_limited``).
* :func:`test_concurrency_cap_bounds_inflight` — the global concurrency cap bounds in-flight
  provider calls through the ``run_provider`` boundary.

``@pytest.mark.integration`` — needs the local Supabase stack; auto-skips when the DB is offline.

**Determinism note (from the 3.4 review):** the global ``llm_budget[today]`` row PERSISTS for the
rest of the UTC day once tripped, so the concurrent test commits to a real DB and resets the
cost-guard tables on setup *and* teardown (and sizes the budget for the accumulated count); the
per-user-cap / rate-limit tests run on the rolled-back ``db_session``. The concurrent waves are
sized so no request ever races the budget boundary (wave 1 is exactly the budget, all admitted; wave
2 starts only after wave 1's increments have all committed), so ``call_count`` is exact, not racy.
"""

from __future__ import annotations

import asyncio
import threading
import time
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable, Iterator

import httpx
import psycopg
import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient, Response
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db.session import UsageSession, async_dsn
from app.deps import DEV_USER_ID, get_db, get_llm_provider, get_usage_db
from app.llm_runner import LLMConcurrencyLimiter, get_llm_limiter, run_provider
from app.main import create_app
from app.quota import _utc_today
from app.ratelimit import InProcessRateLimiter, RateLimiter, get_rate_limiter
from app.repositories.usage import UsageRepository
from app.settings import Settings, get_settings
from lengua_core.llm.fake import FakeLLM
from scripts.seed_e2e import _auth_headers, _supabase_url
from tests.auth_helpers import TEST_JWT_SECRET, auth_header, authenticate_as
from tests.conftest import _skip_if_db_unreachable, database_url

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

# ── Concurrent kill-switch sizing ───────────────────────────────────────────────────────────────
#: Project-wide ceiling for the concurrent test. Small + sized for the accumulated count so the run
#: stays fast and the assertions are exact.
BUDGET = 6
#: Distinct users sharing the global budget (the seeded dev user + two more), each spending part of
#: it — proving the budget is GLOBAL across users, not per-user.
LOAD_USERS = (
    DEV_USER_ID,
    uuid.UUID("00000000-0000-0000-0000-00000000d101"),
    uuid.UUID("00000000-0000-0000-0000-00000000d102"),
)
#: Wave-1 generates per user; ``len(LOAD_USERS) * PER_USER == BUDGET`` so wave 1 spends it exactly.
PER_USER = BUDGET // len(LOAD_USERS)

#: Cost-guard tables reset around the concurrent (committed) test — everything but ``profiles`` (the
#: provisioned users keep their rows) and ``auth.users`` (created once via the Admin API).
_COST_TABLES = (
    "reviews",
    "cards",
    "proficiency",
    "user_settings",
    "llm_usage",
    "languages",
    "llm_budget",
)


def _ensure_auth_user(client: httpx.Client, user_id: str, email: str) -> None:
    """Create a Supabase auth user with the fixed ``user_id`` (idempotent) so its profile FKs."""
    existing = client.get(
        f"{_supabase_url()}/auth/v1/admin/users/{user_id}", headers=_auth_headers()
    )
    if existing.status_code == 200:
        return
    resp = client.post(
        f"{_supabase_url()}/auth/v1/admin/users",
        headers=_auth_headers(),
        json={
            "id": user_id,
            "email": email,
            "password": "load-test-password-123",  # noqa: S106 — fixed local test credential
            "email_confirm": True,
        },
    )
    if resp.status_code in (409, 422):  # raced/duplicate → already present
        return
    resp.raise_for_status()


def _reset_cost_guard() -> None:
    """Truncate the cost-guard / load tables so the global ``llm_budget`` row starts clean."""
    with psycopg.connect(database_url(), autocommit=True) as conn:
        conn.execute(f"TRUNCATE {', '.join(_COST_TABLES)} RESTART IDENTITY CASCADE")


def _provision_load_users() -> None:
    """Create the auth users + ``profiles`` rows the concurrent test's users own rows under."""
    with httpx.Client(timeout=30.0) as client:
        for i, user_id in enumerate(LOAD_USERS):
            _ensure_auth_user(client, str(user_id), f"load-{i}@lengua.test")
    with psycopg.connect(database_url(), autocommit=True) as conn:
        for user_id in LOAD_USERS:
            conn.execute(
                "INSERT INTO profiles (id) VALUES (%s) ON CONFLICT (id) DO NOTHING", (str(user_id),)
            )


def _load_settings() -> Settings:
    """Real JWT verification (test secret) + a tiny global budget; per-user caps/rate kept generous
    so the GLOBAL budget is the binding constraint the concurrent waves exercise."""
    return Settings(  # type: ignore[call-arg]
        _env_file=None,
        supabase_jwt_secret=TEST_JWT_SECRET,
        supabase_jwks_url="",
        global_daily_budget=BUDGET,
        max_generate_per_day=1000,
        default_generate_per_day=1000,
        new_account_day0_generate_cap=1000,
        rate_limit_per_min=1_000_000,
    )


@pytest_asyncio.fixture
async def load_client() -> AsyncIterator[AsyncClient]:
    """A real-session, multi-user ASGI client for the concurrent kill-switch test.

    Unlike the rolled-back fixtures, each request gets its **own** committed session from a
    dedicated engine (so requests run genuinely concurrently), the budget is shared in the real DB,
    and the cost-guard tables are reset on setup + teardown so the persistent counter starts clean.
    """
    _skip_if_db_unreachable()
    _reset_cost_guard()
    _provision_load_users()

    engine = create_async_engine(async_dsn(database_url()))
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    app = create_app()

    async def _override_get_db() -> AsyncIterator[AsyncSession]:
        async with sessions() as session:
            yield session

    async def _override_get_usage_db() -> AsyncIterator[UsageSession]:
        async with sessions() as session:
            yield UsageSession(session)

    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_usage_db] = _override_get_usage_db
    app.dependency_overrides[get_llm_provider] = lambda: FakeLLM()
    app.dependency_overrides[get_settings] = _load_settings
    app.dependency_overrides[get_rate_limiter] = lambda: InProcessRateLimiter(limit=1_000_000)
    app.dependency_overrides[get_llm_limiter] = lambda: LLMConcurrencyLimiter(max_concurrency=8)
    FakeLLM.reset_call_count()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client
    app.dependency_overrides.clear()
    await engine.dispose()
    _reset_cost_guard()


async def test_sustained_concurrent_load_holds_global_killswitch(load_client: AsyncClient) -> None:
    # Each user owns a language so /generate reaches the provider on every admitted call.
    language_ids: dict[uuid.UUID, int] = {}
    for user_id in LOAD_USERS:
        created = await load_client.post(
            "/languages", json={"name": "Spanish", "code": "es"}, headers=auth_header(user_id)
        )
        assert created.status_code == 200, created.text
        language_ids[user_id] = created.json()["id"]

    def _generate(user_id: uuid.UUID) -> Awaitable[Response]:
        return load_client.post(
            "/generate",
            json={"language_id": language_ids[user_id], "words": ["hola"]},
            headers=auth_header(user_id),
        )

    # ── Wave 1: exactly BUDGET concurrent generates (PER_USER each) — all admitted, all spend. ──
    wave1 = [_generate(user_id) for user_id in LOAD_USERS for _ in range(PER_USER)]
    results1 = await asyncio.gather(*wave1)
    assert [r.status_code for r in results1] == [200] * BUDGET, [r.text for r in results1]
    # The operator key was invoked exactly BUDGET times — and never more (bounded by the budget).
    assert FakeLLM.call_count == BUDGET

    # ── Wave 2: more concurrent traffic across ALL users — every request refused, none spends. ──
    wave2 = [_generate(user_id) for user_id in LOAD_USERS for _ in range(PER_USER + 1)]
    results2 = await asyncio.gather(*wave2)
    assert all(r.status_code == 429 for r in results2), [r.status_code for r in results2]
    assert all(r.json()["code"] == "daily_limit_reached" for r in results2)

    # The kill-switch held under concurrency: NOT ONE extra provider call past the global ceiling,
    # so the real operator key can never be billed beyond the (free-tier-safe) budget.
    assert FakeLLM.call_count == BUDGET


# ── Rolled-back single-user harness for the per-user cap + rate-limit bursts ──────────────────────


def _rollback_app(
    db_session: AsyncSession,
    *,
    settings_factory: Callable[[], Settings],
    rate_limiter: RateLimiter,
) -> FastAPI:
    """Build an app on the rolled-back ``db_session`` + ``FakeLLM``, authed as the dev user."""
    app = create_app()

    async def _override_get_db() -> AsyncIterator[AsyncSession]:
        yield db_session

    async def _override_get_usage_db() -> AsyncIterator[UsageSession]:
        yield UsageSession(db_session)

    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_usage_db] = _override_get_usage_db
    app.dependency_overrides[get_llm_provider] = lambda: FakeLLM()
    app.dependency_overrides[get_rate_limiter] = lambda: rate_limiter
    app.dependency_overrides[get_settings] = settings_factory
    app.dependency_overrides[get_llm_limiter] = lambda: LLMConcurrencyLimiter(max_concurrency=8)
    authenticate_as(app, DEV_USER_ID, email_verified=True)
    FakeLLM.reset_call_count()
    return app


async def _new_language(client: AsyncClient) -> int:
    created = await client.post("/languages", json={"name": "Spanish", "code": "es"})
    assert created.status_code == 200, created.text
    return int(created.json()["id"])


@pytest.fixture
def _seed_dev() -> Iterator[None]:
    """Commit the dev profile so the rolled-back tests' FK-bound inserts resolve."""
    from scripts.seed_dev_user import seed_dev_user

    _skip_if_db_unreachable()
    seed_dev_user()
    yield


async def test_per_user_daily_cap_never_exceeded_under_burst(
    db_session: AsyncSession, _seed_dev: None
) -> None:
    cap = 3

    def _settings() -> Settings:
        return Settings(  # type: ignore[call-arg]
            _env_file=None,
            global_daily_budget=1_000,
            max_generate_per_day=50,
            default_generate_per_day=cap,
            new_account_day0_generate_cap=cap,
        )

    app = _rollback_app(
        db_session, settings_factory=_settings, rate_limiter=InProcessRateLimiter(limit=1_000_000)
    )
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        language_id = await _new_language(client)
        body = {"language_id": language_id, "words": ["hola"]}
        statuses = [(await client.post("/generate", json=body)).status_code for _ in range(cap + 3)]

    # Exactly ``cap`` admitted (200); every request past the cap is refused — never exceeded.
    assert statuses == [200] * cap + [429] * 3
    assert FakeLLM.call_count == cap
    today = _utc_today()
    assert (
        await UsageRepository(db_session).get_user_daily_count(DEV_USER_ID, "generate", today)
        == cap
    )


async def test_rate_limit_holds_under_burst(db_session: AsyncSession, _seed_dev: None) -> None:
    limit = 4

    def _settings() -> Settings:
        return Settings(  # type: ignore[call-arg]
            _env_file=None,
            global_daily_budget=1_000,
            max_generate_per_day=1_000,
            default_generate_per_day=1_000,
            new_account_day0_generate_cap=1_000,
        )

    # A frozen clock keeps every hit inside one window, so the (limit+1)th is rejected.
    rate_limiter = InProcessRateLimiter(limit=limit, clock=lambda: 0.0)
    app = _rollback_app(db_session, settings_factory=_settings, rate_limiter=rate_limiter)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        language_id = await _new_language(client)
        body = {"language_id": language_id, "words": ["hola"]}
        responses = [await client.post("/generate", json=body) for _ in range(limit + 2)]

    assert [r.status_code for r in responses] == [200] * limit + [429, 429]
    over_limit = responses[limit]
    assert over_limit.json() == {"code": "rate_limited"}
    assert "Retry-After" in over_limit.headers
    assert FakeLLM.call_count == limit  # only the admitted calls reached the provider


# ── Concurrency cap bounds in-flight provider calls through the run_provider boundary ─────────────


class _SlowProvider:
    """A slow blocking stand-in recording the high-water-mark of concurrent in-flight calls.

    Runs in worker threads (``asyncio.to_thread`` under the cap), so the in-flight counter is
    guarded by a :class:`threading.Lock`; a real :func:`time.sleep` makes overlapping calls coexist.
    """

    def __init__(self, hold: float = 0.05) -> None:
        self._hold = hold
        self._lock = threading.Lock()
        self._in_flight = 0
        self.max_in_flight = 0

    def __call__(self) -> int:
        with self._lock:
            self._in_flight += 1
            self.max_in_flight = max(self.max_in_flight, self._in_flight)
        try:
            time.sleep(self._hold)
            return self.max_in_flight
        finally:
            with self._lock:
                self._in_flight -= 1


async def test_concurrency_cap_bounds_inflight() -> None:
    cap = 2
    limiter = LLMConcurrencyLimiter(max_concurrency=cap)
    provider = _SlowProvider(hold=0.05)

    # Fire six concurrent provider calls THROUGH the run_provider boundary; the semaphore must never
    # let more than ``cap`` run at once (no DB, no real LLM — a local slow stand-in).
    await asyncio.gather(*(run_provider(limiter, FakeLLM(), None, provider) for _ in range(6)))

    assert provider.max_in_flight <= cap  # the cap held under sustained concurrency
    assert provider.max_in_flight >= 2  # …and calls genuinely overlapped (it is a real bound)
