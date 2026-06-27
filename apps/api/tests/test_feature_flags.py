"""Feature flags — typed accessor, public endpoint, dark-route gating, and the lockdown (task 6.9).

Layered like the rest of the suite:

* **Unit (offline)** — the :class:`~app.feature_flags.FeatureFlags` accessor (env default off, table
  override wins, the TTL cache + the *toggle-without-redeploy* refresh proven against an injected
  clock — 6.9.3), the public ``GET /feature-flags`` map, and the experimental dark route's
  ``404``-when-off / ``200``-when-on gate (6.9.2). All use injected fakes (reader / clock / env /
  dependency overrides), so they need no database.
* **Integration (``@pytest.mark.integration``)** — the *real* DB read path and the SECURITY proof
  that the global ``feature_flags`` table is locked down: ``authenticated`` / ``anon`` cannot read
  or write it (a user must never flip their own flags). These auto-skip when the Supabase stack is
  unreachable (see ``tests/conftest``).
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncIterator, Callable

import psycopg
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

import app.feature_flags as ff
from app.feature_flags import (
    KNOWN_FLAGS,
    MIN_TTL_SECONDS,
    PUBLIC_FLAGS,
    WORD_OF_THE_DAY,
    FeatureFlags,
    FlagSpec,
    get_feature_flags,
    parse_bool,
    read_flags_from_db,
    reset_feature_flags,
)
from app.main import create_app
from tests.auth_helpers import authenticate_as
from tests.conftest import database_url
from tests.rls_helpers import (
    acting_as,
    has_table_privilege,
    policies_by_table,
    rls_status,
)

# ── Helpers ───────────────────────────────────────────────────────────────────────────────────────


def make_flags(
    *,
    table: dict[str, bool] | None = None,
    env: dict[str, str] | None = None,
    ttl: float = 30.0,
    clock: Callable[[], float] | None = None,
) -> FeatureFlags:
    """A :class:`FeatureFlags` whose table layer is a fixed dict and whose clock is frozen at 0."""
    snapshot = dict(table or {})

    async def reader() -> dict[str, bool]:
        return dict(snapshot)

    return FeatureFlags(reader=reader, ttl_seconds=ttl, clock=clock or (lambda: 0.0), env=env or {})


# ── parse_bool ────────────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("value", ["1", "true", "TRUE", " yes ", "on", "t", "y"])
def test_parse_bool_truthy(value: str) -> None:
    assert parse_bool(value) is True


@pytest.mark.parametrize("value", [None, "", "0", "false", "no", "off", "nope"])
def test_parse_bool_falsy(value: str | None) -> None:
    assert parse_bool(value) is False


# ── FeatureFlags resolution (default off · env default · table override) ──────────────


@pytest.mark.asyncio
async def test_flag_defaults_off() -> None:
    """With no env var and no table row, a known flag resolves OFF."""
    flags = make_flags()
    assert await flags.is_enabled(WORD_OF_THE_DAY) is False


@pytest.mark.asyncio
async def test_env_default_enables_flag() -> None:
    """A truthy ``FEATURE_*`` env var flips the default on (still overridable by the table)."""
    flags = make_flags(env={WORD_OF_THE_DAY.env_var: "true"})
    assert await flags.is_enabled(WORD_OF_THE_DAY) is True


@pytest.mark.asyncio
async def test_table_row_overrides_env_default() -> None:
    """A ``feature_flags`` row wins over the env default — both on-over-off and off-over-on."""
    on_over_off = make_flags(table={WORD_OF_THE_DAY.name: True}, env={})
    assert await on_over_off.is_enabled(WORD_OF_THE_DAY) is True

    off_over_on = make_flags(
        table={WORD_OF_THE_DAY.name: False}, env={WORD_OF_THE_DAY.env_var: "1"}
    )
    assert await off_over_on.is_enabled(WORD_OF_THE_DAY) is False


@pytest.mark.asyncio
async def test_public_map_exposes_only_public_flags() -> None:
    """``public_map`` returns the resolved boolean for every PUBLIC flag and nothing else."""
    flags = make_flags(table={WORD_OF_THE_DAY.name: True})
    assert await flags.public_map() == {WORD_OF_THE_DAY.name: True}


# ── Public-surface isolation: a server-only flag can NEVER leak publicly ──────────────
#
# Guards the one residual risk: future PUBLIC_FLAGS drift exposing a server-only flag to anonymous
# clients. A KNOWN-but-NOT-public flag, declared only for these tests, must stay absent from the
# public surface even when it is genuinely enabled (env AND table).
_SERVER_ONLY_FLAG = FlagSpec(
    name="server_only_test_flag",
    env_var="FEATURE_SERVER_ONLY_TEST",
    description="A server-only flag (never in PUBLIC_FLAGS) — proves the public map can't leak it.",
)


def test_every_public_flag_is_a_known_flag() -> None:
    """Every PUBLIC flag is registered in KNOWN_FLAGS (a public name must always resolve)."""
    assert {f.name for f in PUBLIC_FLAGS} <= {f.name for f in KNOWN_FLAGS}


@pytest.mark.asyncio
async def test_public_map_never_leaks_a_non_public_flag() -> None:
    """An enabled server-only flag (env AND table) is ABSENT from ``public_map``.

    ``public_map`` iterates PUBLIC_FLAGS only, so a flag outside that set can never appear — even if
    it is genuinely on. This is the structural lock against a server-only flag leaking to clients.
    """
    flags = make_flags(
        table={_SERVER_ONLY_FLAG.name: True, WORD_OF_THE_DAY.name: True},
        env={_SERVER_ONLY_FLAG.env_var: "true"},
    )
    # The server-only flag is genuinely ENABLED for server-side resolution...
    assert await flags.is_enabled(_SERVER_ONLY_FLAG) is True
    # ...yet the public map exposes ONLY the public flag names — never the server-only one.
    public = await flags.public_map()
    assert _SERVER_ONLY_FLAG.name not in public
    assert set(public) == {f.name for f in PUBLIC_FLAGS}


# ── TTL cache + the toggle-without-redeploy refresh (6.9.3) ──────────────


@pytest.mark.asyncio
async def test_table_snapshot_is_cached_within_the_ttl_then_refreshes() -> None:
    """A table change is invisible within the TTL, then picked up once the injected clock advances.

    This is the deterministic, as-code proof for 6.9.3: an operator writing the ``feature_flags``
    row flips the resolved value within one ``FEATURE_FLAG_TTL_SECONDS`` window — **no redeploy** —
    and not a microsecond before (the cache holds the prior snapshot until then).
    """
    reads = {"n": 0}
    state = {WORD_OF_THE_DAY.name: False}
    now = {"t": 0.0}

    async def reader() -> dict[str, bool]:
        reads["n"] += 1
        return dict(state)

    flags = FeatureFlags(reader=reader, ttl_seconds=30.0, clock=lambda: now["t"], env={})

    # First resolution reads the table (off).
    assert await flags.is_enabled(WORD_OF_THE_DAY) is False
    assert reads["n"] == 1

    # An operator flips the row on — but within the TTL the cached snapshot still says off.
    state[WORD_OF_THE_DAY.name] = True
    assert await flags.is_enabled(WORD_OF_THE_DAY) is False
    assert reads["n"] == 1

    # Advance the clock past the TTL → the next resolution re-reads and now sees the new value.
    now["t"] = 31.0
    assert await flags.is_enabled(WORD_OF_THE_DAY) is True
    assert reads["n"] == 2


@pytest.mark.asyncio
async def test_non_positive_ttl_is_floored_against_db_hammering() -> None:
    """``FEATURE_FLAG_TTL_SECONDS<=0`` is clamped to a floor so the public endpoint isn't a hammer.

    Without the floor, a TTL of 0 would re-read ``feature_flags`` on every unauthenticated request.
    Clamped, a second resolution inside the floor window reuses the cache; only past the floor does
    it refresh — so an anonymous caller can't turn config into one DB query per request.
    """
    reads = {"n": 0}
    now = {"t": 0.0}

    async def reader() -> dict[str, bool]:
        reads["n"] += 1
        return {}

    flags = FeatureFlags(reader=reader, ttl_seconds=0.0, clock=lambda: now["t"], env={})
    await flags.is_enabled(WORD_OF_THE_DAY)
    # Within the floor window: served from cache, no second DB read.
    now["t"] = MIN_TTL_SECONDS / 2
    await flags.is_enabled(WORD_OF_THE_DAY)
    assert reads["n"] == 1
    # Past the floor: refreshes exactly once.
    now["t"] = MIN_TTL_SECONDS + 0.001
    await flags.is_enabled(WORD_OF_THE_DAY)
    assert reads["n"] == 2


@pytest.mark.asyncio
async def test_invalidate_forces_a_reread() -> None:
    """``invalidate()`` drops the snapshot so the next resolution re-reads immediately."""
    reads = {"n": 0}

    async def reader() -> dict[str, bool]:
        reads["n"] += 1
        return {}

    flags = FeatureFlags(reader=reader, ttl_seconds=30.0, clock=lambda: 0.0, env={})
    await flags.is_enabled(WORD_OF_THE_DAY)
    assert reads["n"] == 1
    flags.invalidate()
    await flags.is_enabled(WORD_OF_THE_DAY)
    assert reads["n"] == 2


@pytest.mark.asyncio
async def test_concurrent_resolution_reads_the_table_once() -> None:
    """A burst of concurrent resolutions with a cold cache makes exactly ONE table read."""
    reads = {"n": 0}

    async def reader() -> dict[str, bool]:
        reads["n"] += 1
        await asyncio.sleep(0)  # yield so the second coroutine reaches the lock while we read
        return {}

    flags = FeatureFlags(reader=reader, ttl_seconds=30.0, clock=lambda: 0.0, env={})
    await asyncio.gather(flags.is_enabled(WORD_OF_THE_DAY), flags.is_enabled(WORD_OF_THE_DAY))
    assert reads["n"] == 1


# ── read_flags_from_db (stubbed sessionmaker — the DB seam, offline) ──────────────


class _FakeResult:
    def __init__(self, rows: list[dict[str, object]]) -> None:
        self._rows = rows

    def mappings(self) -> list[dict[str, object]]:
        return self._rows


class _FakeSession:
    def __init__(self, rows: list[dict[str, object]]) -> None:
        self._rows = rows

    async def __aenter__(self) -> _FakeSession:
        return self

    async def __aexit__(self, *exc: object) -> bool:
        return False

    async def execute(self, _stmt: object) -> _FakeResult:
        return _FakeResult(self._rows)


@pytest.mark.asyncio
async def test_read_flags_from_db_maps_rows(monkeypatch: pytest.MonkeyPatch) -> None:
    """The DB reader maps ``(name, enabled)`` rows into ``{name: bool}`` on a privileged session."""
    rows: list[dict[str, object]] = [
        {"name": "word_of_the_day", "enabled": True},
        {"name": "other", "enabled": False},
    ]
    monkeypatch.setattr(ff, "get_sessionmaker", lambda: lambda: _FakeSession(rows))
    assert await read_flags_from_db() == {"word_of_the_day": True, "other": False}


@pytest.mark.asyncio
async def test_read_flags_from_db_is_fail_safe(monkeypatch: pytest.MonkeyPatch) -> None:
    """If the table can't be read, the reader returns ``{}`` so resolution falls back to env."""

    def boom() -> object:
        raise RuntimeError("db down")

    monkeypatch.setattr(ff, "get_sessionmaker", boom)
    assert await read_flags_from_db() == {}


# ── Singleton wiring ──────────────


def test_get_feature_flags_is_a_singleton() -> None:
    """The dependency returns the same cached accessor until ``reset_feature_flags`` clears it."""
    reset_feature_flags()
    try:
        first = get_feature_flags()
        assert get_feature_flags() is first
        reset_feature_flags()
        assert get_feature_flags() is not first
    finally:
        reset_feature_flags()


# ── HTTP surface: GET /feature-flags + the experimental dark route (6.9.1 / 6.9.2) ──────────────


@pytest_asyncio.fixture
async def public_client() -> AsyncIterator[tuple[AsyncClient, dict[str, bool]]]:
    """A client whose feature-flag accessor is a controllable in-memory fake (no DB, no auth)."""
    app = create_app(include_test_routes=False)
    table: dict[str, bool] = {}
    app.dependency_overrides[get_feature_flags] = lambda: make_flags(table=table)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client, table
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_feature_flags_endpoint_defaults_off(
    public_client: tuple[AsyncClient, dict[str, bool]],
) -> None:
    client, _table = public_client
    response = await client.get("/feature-flags")
    assert response.status_code == 200
    assert response.json() == {WORD_OF_THE_DAY.name: False}


@pytest.mark.asyncio
async def test_feature_flags_endpoint_reflects_table(
    public_client: tuple[AsyncClient, dict[str, bool]],
) -> None:
    client, table = public_client
    table[WORD_OF_THE_DAY.name] = True
    response = await client.get("/feature-flags")
    assert response.status_code == 200
    assert response.json() == {WORD_OF_THE_DAY.name: True}


@pytest.mark.asyncio
async def test_feature_flags_endpoint_never_leaks_a_non_public_flag(
    public_client: tuple[AsyncClient, dict[str, bool]],
) -> None:
    """Even with a server-only override in the table, ``GET /feature-flags`` returns only PUBLIC.

    The end-to-end guard for the anonymous public surface: a server-only flag enabled in the table
    is never serialized to the unauthenticated client.
    """
    client, table = public_client
    table[_SERVER_ONLY_FLAG.name] = True  # a server-only override, must not surface
    table[WORD_OF_THE_DAY.name] = True
    response = await client.get("/feature-flags")
    assert response.status_code == 200
    body = response.json()
    assert _SERVER_ONLY_FLAG.name not in body
    assert set(body) == {f.name for f in PUBLIC_FLAGS}


@pytest_asyncio.fixture
async def authed_client() -> AsyncIterator[tuple[AsyncClient, dict[str, bool]]]:
    """An authenticated client (no DB) whose feature-flag table layer is a controllable fake."""
    app = create_app(include_test_routes=False)
    authenticate_as(app, uuid.uuid4())
    table: dict[str, bool] = {}
    app.dependency_overrides[get_feature_flags] = lambda: make_flags(table=table)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client, table
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_dark_route_is_absent_when_flag_off(
    authed_client: tuple[AsyncClient, dict[str, bool]],
) -> None:
    """With the flag off (the default), the experimental route 404s — it ships dark (6.9.2)."""
    client, _table = authed_client
    response = await client.get("/experimental/word-of-the-day")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_dark_route_is_exposed_when_flag_on(
    authed_client: tuple[AsyncClient, dict[str, bool]],
) -> None:
    """Flipping the flag on exposes the route + payload (no redeploy) — the other half of 6.9.2."""
    client, table = authed_client
    table[WORD_OF_THE_DAY.name] = True
    response = await client.get("/experimental/word-of-the-day")
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"word", "translation", "note"}


# ── Integration: the real DB read path + the lockdown (SECURITY) ──────────────


@pytest.mark.integration
@pytest.mark.asyncio
async def test_read_flags_from_db_reads_committed_rows() -> None:
    """The production reader, on the real privileged app session, sees a committed flag row."""
    from app.db.session import dispose_engine

    await dispose_engine()  # rebuild the engine on THIS test's event loop
    try:
        with psycopg.connect(database_url(), autocommit=True) as conn:
            conn.execute("DELETE FROM feature_flags WHERE name = %s", (WORD_OF_THE_DAY.name,))
            conn.execute(
                "INSERT INTO feature_flags (name, enabled) VALUES (%s, %s)",
                (WORD_OF_THE_DAY.name, True),
            )
        overrides = await read_flags_from_db()
        assert overrides.get(WORD_OF_THE_DAY.name) is True
    finally:
        with psycopg.connect(database_url(), autocommit=True) as conn:
            conn.execute("DELETE FROM feature_flags WHERE name = %s", (WORD_OF_THE_DAY.name,))
        await dispose_engine()


@pytest.mark.integration
def test_feature_flags_table_is_deny_by_default_on_live_stack() -> None:
    """``feature_flags`` has RLS enabled with NO policy (deny-by-default), like llm_budget."""
    with psycopg.connect(database_url(), autocommit=True) as conn:
        status = rls_status(conn)
        policies = policies_by_table(conn)
    assert status.get("feature_flags") is True, "feature_flags must have RLS enabled"
    assert not policies.get("feature_flags"), "feature_flags must have NO policy (deny-all)"


@pytest.mark.integration
def test_authenticated_and_anon_have_no_privileges_on_feature_flags() -> None:
    """Neither ``authenticated`` nor ``anon`` holds ANY table privilege — reads/writes server-only.

    SECURITY: ``feature_flags`` is GLOBAL operator config, so a logged-in user must never be able to
    enable a flag for everyone (nor read the raw table). The flag state reaches clients only via the
    public ``GET /feature-flags`` API map.
    """
    with psycopg.connect(database_url(), autocommit=True) as conn:
        missing = [
            f"{role}:{priv}"
            for role in ("authenticated", "anon")
            for priv in ("SELECT", "INSERT", "UPDATE", "DELETE")
            if has_table_privilege(conn, role, "feature_flags", priv)
        ]
    assert not missing, (
        f"authenticated/anon unexpectedly hold privileges on feature_flags: {missing}"
    )


@pytest.mark.integration
def test_authenticated_role_cannot_write_or_read_feature_flags() -> None:
    """A real ``authenticated`` session is denied at runtime (not just by the grant catalog)."""
    uid = uuid.uuid4()
    with acting_as(uid) as conn, pytest.raises(psycopg.errors.InsufficientPrivilege):
        conn.execute("INSERT INTO feature_flags (name, enabled) VALUES ('hacked', true)")
    with acting_as(uid) as conn, pytest.raises(psycopg.errors.InsufficientPrivilege):
        conn.execute("SELECT name FROM feature_flags")
