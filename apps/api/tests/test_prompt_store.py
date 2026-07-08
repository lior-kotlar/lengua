"""DB-backed prompts with versioning — the store, the builders' fallback, and the lockdown (#80).

Layered like the feature-flags suite:

* **Unit (offline)** — the pure ``lengua_core.prompts`` builders' source-hook fallback (code default
  when no source / a source ``None``), and the :class:`~app.prompt_store.PromptStore` accessor: warm
  + synchronous ``get``, the TTL cache + the *change-without-redeploy* refresh (against an injected
  clock), the TTL floor, ``invalidate``, concurrent-warm-reads-once, and ``resolve`` for the ``-1``
  (active) and pinned-version paths. All use injected fakes, so they need no database.
* **Integration (``@pytest.mark.integration``)** — the *real* DB read path against the seeded
  ``prompt_versions`` table: the seed matches the code defaults, exactly one active version per key,
  a new active version changes what the store resolves (the acceptance criterion), and the SECURITY
  proof that the global table is locked down (``authenticated``/``anon`` cannot read or write it).
  These auto-skip when the Supabase stack is unreachable (see ``tests/conftest``).
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Awaitable, Callable

import psycopg
import pytest

import app.prompt_store as ps
from app.prompt_store import (
    ACTIVE_VERSION,
    MIN_TTL_SECONDS,
    PromptStore,
    get_prompt_store,
    read_active_prompts_from_db,
    read_pinned_prompt_from_db,
    reset_prompt_store,
    warm_prompt_store,
)
from lengua_core import prompts
from tests.conftest import database_url

# ── Helpers ─────────────────────────────────────────────────────────────────────────────────────


def make_store(
    *,
    active: dict[str, str] | None = None,
    ttl: float = 60.0,
    clock: Callable[[], float] | None = None,
    pinned_reader: Callable[[str, int], Awaitable[str | None]] | None = None,
) -> PromptStore:
    """A :class:`PromptStore` whose active layer is a fixed dict and whose clock is frozen at 0."""
    snapshot = dict(active or {})

    async def reader() -> dict[str, str]:
        return dict(snapshot)

    return PromptStore(
        reader=reader,
        ttl_seconds=ttl,
        clock=clock or (lambda: 0.0),
        pinned_reader=pinned_reader,
    )


# ── The pure builders: source-hook fallback (lengua_core.prompts) ─────────────────────────────────


def test_resolve_fragment_falls_back_to_code_default_with_no_source() -> None:
    """With no installed source, every fragment resolves to its in-code default."""
    prompts.set_prompt_source(None)
    for key in prompts.PROMPT_KEYS:
        assert prompts.resolve_fragment(key) == prompts.CODE_DEFAULTS[key]


def test_resolve_fragment_uses_override_when_source_returns_one() -> None:
    """An installed source's non-``None`` return overrides the code default for that key only."""

    def source(key: str) -> str | None:
        return "OVERRIDE" if key == prompts.KEY_RULES else None

    prompts.set_prompt_source(source)
    try:
        assert prompts.resolve_fragment(prompts.KEY_RULES) == "OVERRIDE"
        # A key the source declines (returns None for) still falls back to code.
        assert prompts.resolve_fragment(prompts.KEY_OUTPUT_FORMAT) == prompts.OUTPUT_FORMAT
    finally:
        prompts.set_prompt_source(None)


def test_system_instruction_uses_override_and_keeps_assembly_in_code() -> None:
    """A ``rules`` override changes the text; the builder still assembles/interpolates in code."""

    def source(key: str) -> str | None:
        return "NEW RULES" if key == prompts.KEY_RULES else None

    prompts.set_prompt_source(source)
    try:
        out = prompts.system_instruction("Spanish", level="A2")
    finally:
        prompts.set_prompt_source(None)
    assert out.startswith("NEW RULES\n\n")
    # The generation + level + output fragments (code defaults) are still assembled + interpolated.
    assert "learn Spanish" in out
    assert "CEFR level A2" in out


def test_suggestion_instruction_override_template_is_interpolated() -> None:
    """A ``suggestion_instruction`` override template gets its sub-blocks filled in code."""

    def source(key: str) -> str | None:
        if key == prompts.KEY_SUGGESTION_INSTRUCTION:
            return "PICK {count} IN {language} @ {level_band}.{topic_line} {known_block}"
        return None

    prompts.set_prompt_source(source)
    try:
        out = prompts.suggestion_instruction("French", "B1", ["a", "b"], 4, topic="travel")
    finally:
        prompts.set_prompt_source(None)
    assert out.startswith("PICK 4 IN French @ B1.")
    assert "Focus on the topic or domain: travel." in out
    assert "do NOT include any of them" in out


# ── PromptStore: warm + synchronous get ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_returns_none_before_warm() -> None:
    """A cold store's synchronous ``get`` returns ``None`` (→ the builder uses the code default)."""
    store = make_store(active={prompts.KEY_RULES: "X"})
    assert store.get(prompts.KEY_RULES) is None  # not warmed yet


@pytest.mark.asyncio
async def test_warm_then_get_returns_active_content() -> None:
    """After ``warm``, ``get`` returns the active content for a seeded key, ``None`` for others."""
    store = make_store(active={prompts.KEY_RULES: "ACTIVE RULES"})
    await store.warm()
    assert store.get(prompts.KEY_RULES) == "ACTIVE RULES"
    assert store.get(prompts.KEY_OUTPUT_FORMAT) is None


@pytest.mark.asyncio
async def test_install_wires_get_as_the_prompt_source() -> None:
    """``install`` makes the builders resolve overrides from this store's warmed snapshot."""
    store = make_store(active={prompts.KEY_RULES: "STORE RULES"})
    await store.warm()
    store.install()
    try:
        assert prompts.resolve_fragment(prompts.KEY_RULES) == "STORE RULES"
        # A key not in the active snapshot still falls back to code.
        assert prompts.resolve_fragment(prompts.KEY_OUTPUT_FORMAT) == prompts.OUTPUT_FORMAT
    finally:
        prompts.set_prompt_source(None)


# ── TTL cache + the change-without-redeploy refresh (the acceptance criterion, offline) ──────────


@pytest.mark.asyncio
async def test_active_snapshot_is_cached_within_ttl_then_refreshes() -> None:
    """An active-version change is invisible within the TTL, then picked up once the clock advances.

    The deterministic, as-code proof of the #80 acceptance criterion: appending a new active version
    changes generation within one ``PROMPT_CACHE_TTL_SECONDS`` window — no redeploy — not before.
    """
    reads = {"n": 0}
    state = {prompts.KEY_RULES: "v1"}
    now = {"t": 0.0}

    async def reader() -> dict[str, str]:
        reads["n"] += 1
        return dict(state)

    store = PromptStore(reader=reader, ttl_seconds=60.0, clock=lambda: now["t"])
    await store.warm()
    assert store.get(prompts.KEY_RULES) == "v1"
    assert reads["n"] == 1

    # An operator flips the active version — but within the TTL the cached snapshot still says v1.
    state[prompts.KEY_RULES] = "v2"
    await store.warm()
    assert store.get(prompts.KEY_RULES) == "v1"
    assert reads["n"] == 1

    # Advance past the TTL → the next warm re-reads and now sees the new active content.
    now["t"] = 61.0
    await store.warm()
    assert store.get(prompts.KEY_RULES) == "v2"
    assert reads["n"] == 2


@pytest.mark.asyncio
async def test_non_positive_ttl_is_floored() -> None:
    """``PROMPT_CACHE_TTL_SECONDS <= 0`` is clamped to a floor so we don't re-read each call."""
    reads = {"n": 0}
    now = {"t": 0.0}

    async def reader() -> dict[str, str]:
        reads["n"] += 1
        return {}

    store = PromptStore(reader=reader, ttl_seconds=0.0, clock=lambda: now["t"])
    await store.warm()
    now["t"] = MIN_TTL_SECONDS / 2
    await store.warm()
    assert reads["n"] == 1  # within the floor window: cached
    now["t"] = MIN_TTL_SECONDS + 0.001
    await store.warm()
    assert reads["n"] == 2  # past the floor: refreshed


@pytest.mark.asyncio
async def test_invalidate_forces_a_reread() -> None:
    """``invalidate()`` drops the snapshot so the next ``warm`` re-reads immediately."""
    reads = {"n": 0}

    async def reader() -> dict[str, str]:
        reads["n"] += 1
        return {}

    store = PromptStore(reader=reader, ttl_seconds=60.0, clock=lambda: 0.0)
    await store.warm()
    assert reads["n"] == 1
    store.invalidate()
    assert store.get(prompts.KEY_RULES) is None  # snapshot dropped
    await store.warm()
    assert reads["n"] == 2


@pytest.mark.asyncio
async def test_concurrent_warm_reads_the_table_once() -> None:
    """A burst of concurrent warms with a cold cache makes exactly ONE table read."""
    reads = {"n": 0}

    async def reader() -> dict[str, str]:
        reads["n"] += 1
        await asyncio.sleep(0)  # yield so the second coroutine reaches the lock while we read
        return {}

    store = PromptStore(reader=reader, ttl_seconds=60.0, clock=lambda: 0.0)
    await asyncio.gather(store.warm(), store.warm())
    assert reads["n"] == 1


# ── resolve: -1 → active, positive → pinned, both with a code fallback ───────────────────────────


@pytest.mark.asyncio
async def test_resolve_default_uses_active_version() -> None:
    """``resolve(key)`` (default ``version=-1``) returns the active content, warming as needed."""
    store = make_store(active={prompts.KEY_RULES: "ACTIVE"})
    assert await store.resolve(prompts.KEY_RULES) == "ACTIVE"
    assert ACTIVE_VERSION == -1


@pytest.mark.asyncio
async def test_resolve_active_falls_back_to_code_default_when_key_absent() -> None:
    """``resolve`` for a key with no active row falls back to the code default."""
    store = make_store(active={})
    assert await store.resolve(prompts.KEY_OUTPUT_FORMAT) == prompts.OUTPUT_FORMAT


@pytest.mark.asyncio
async def test_resolve_positive_version_pins_that_version() -> None:
    """A positive ``version`` reads that exact pinned row (reproducibility / A-B)."""
    seen: list[tuple[str, int]] = []

    async def pinned(key: str, version: int) -> str | None:
        seen.append((key, version))
        return f"PINNED v{version}"

    store = make_store(active={prompts.KEY_RULES: "ACTIVE"}, pinned_reader=pinned)
    assert await store.resolve(prompts.KEY_RULES, version=3) == "PINNED v3"
    assert seen == [(prompts.KEY_RULES, 3)]


@pytest.mark.asyncio
async def test_resolve_positive_version_missing_falls_back_to_code_default() -> None:
    """A pinned version that doesn't exist (reader returns ``None``) falls back to code default."""

    async def pinned(_key: str, _version: int) -> str | None:
        return None

    store = make_store(pinned_reader=pinned)
    assert await store.resolve(prompts.KEY_RULES, version=99) == prompts.RULES_PROMPT


# ── read_active_prompts_from_db (stubbed sessionmaker — the DB seam, offline) ─────────────────────


class _FakeResult:
    def __init__(self, rows: list[dict[str, object]]) -> None:
        self._rows = rows

    def mappings(self) -> list[dict[str, object]]:
        return self._rows

    def first(self) -> tuple[object, ...] | None:
        return None if not self._rows else tuple(self._rows[0].values())


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
async def test_read_active_prompts_from_db_maps_rows(monkeypatch: pytest.MonkeyPatch) -> None:
    """The active reader maps privileged-session ``(key, content)`` rows into ``{key: content}``."""
    rows: list[dict[str, object]] = [
        {"key": "rules", "content": "R"},
        {"key": "output_format", "content": "O"},
    ]
    monkeypatch.setattr(ps, "get_sessionmaker", lambda: lambda: _FakeSession(rows))
    assert await read_active_prompts_from_db() == {"rules": "R", "output_format": "O"}


@pytest.mark.asyncio
async def test_read_active_prompts_from_db_is_fail_safe(monkeypatch: pytest.MonkeyPatch) -> None:
    """If the table can't be read, the reader returns ``{}`` so builders use code defaults."""

    def boom() -> object:
        raise RuntimeError("db down")

    monkeypatch.setattr(ps, "get_sessionmaker", boom)
    assert await read_active_prompts_from_db() == {}


@pytest.mark.asyncio
async def test_read_pinned_prompt_from_db_returns_content(monkeypatch: pytest.MonkeyPatch) -> None:
    """The pinned reader returns the single row's content."""
    rows: list[dict[str, object]] = [{"content": "PINNED"}]
    monkeypatch.setattr(ps, "get_sessionmaker", lambda: lambda: _FakeSession(rows))
    assert await read_pinned_prompt_from_db("rules", 2) == "PINNED"


@pytest.mark.asyncio
async def test_read_pinned_prompt_from_db_none_when_absent(monkeypatch: pytest.MonkeyPatch) -> None:
    """The pinned reader returns ``None`` for a missing (key, version)."""
    monkeypatch.setattr(ps, "get_sessionmaker", lambda: lambda: _FakeSession([]))
    assert await read_pinned_prompt_from_db("rules", 2) is None


@pytest.mark.asyncio
async def test_read_pinned_prompt_from_db_is_fail_safe(monkeypatch: pytest.MonkeyPatch) -> None:
    """A pinned-read failure returns ``None`` (→ code default), never raises."""

    def boom() -> object:
        raise RuntimeError("db down")

    monkeypatch.setattr(ps, "get_sessionmaker", boom)
    assert await read_pinned_prompt_from_db("rules", 2) is None


# ── Singleton wiring + warm_prompt_store best-effort ─────────────────────────────────────────────


def test_get_prompt_store_is_a_singleton() -> None:
    """The accessor returns the same cached store until ``reset_prompt_store`` clears it."""
    reset_prompt_store()
    try:
        first = get_prompt_store()
        assert get_prompt_store() is first
        reset_prompt_store()
        assert get_prompt_store() is not first
    finally:
        reset_prompt_store()


def test_reset_prompt_store_clears_the_installed_source() -> None:
    """``reset_prompt_store`` clears the ``lengua_core.prompts`` source so code defaults resume."""
    prompts.set_prompt_source(lambda _k: "LEAK")
    reset_prompt_store()
    assert prompts.resolve_fragment(prompts.KEY_RULES) == prompts.RULES_PROMPT


@pytest.mark.asyncio
async def test_warm_prompt_store_is_best_effort(monkeypatch: pytest.MonkeyPatch) -> None:
    """A failing store warm is swallowed — a prompt refresh must never break a generation."""

    class _Boom:
        async def warm(self) -> dict[str, str]:
            raise RuntimeError("boom")

    monkeypatch.setattr(ps, "get_prompt_store", lambda: _Boom())
    await warm_prompt_store()  # must not raise


# ── Integration: the real DB read path + the seed round-trip + the lockdown (SECURITY) ──────────


@pytest.mark.integration
def test_seed_matches_code_defaults_and_one_active_per_key() -> None:
    """The seeded ``prompt_versions`` matches the code defaults: v1 active, one row per key."""
    with psycopg.connect(database_url(), autocommit=True) as conn:
        rows = conn.execute(
            "SELECT key, version, content, is_active FROM prompt_versions WHERE is_active"
        ).fetchall()
    active = {str(r[0]): (int(r[1]), str(r[2])) for r in rows}
    # Exactly the known keys are active, each at version 1 with content == the code default.
    assert set(active) == set(prompts.PROMPT_KEYS)
    for key in prompts.PROMPT_KEYS:
        version, content = active[key]
        assert version == 1, f"{key} should be active at version 1"
        assert content == prompts.CODE_DEFAULTS[key], f"{key} seed drifted from the code default"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_read_active_prompts_reads_seeded_rows() -> None:
    """The production reader, on the real privileged app session, sees the seeded active rows."""
    from app.db.session import dispose_engine

    await dispose_engine()  # rebuild the engine on THIS test's event loop
    try:
        active = await read_active_prompts_from_db()
        for key in prompts.PROMPT_KEYS:
            assert active.get(key) == prompts.CODE_DEFAULTS[key]
    finally:
        await dispose_engine()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_new_active_version_changes_resolution_without_redeploy() -> None:
    """Appending a new active version changes what the store resolves — the acceptance criterion.

    Proves the end-to-end DB path: with a fresh (TTL-cold) store, flipping the active ``rules`` row
    to a new version makes the store resolve the new content — no code change, no redeploy. The row
    is inserted then cleaned up so the shared local stack is left with only the seeded v1 active.
    """
    from app.db.session import dispose_engine

    await dispose_engine()
    marker = f"OVERRIDE-{uuid.uuid4().hex[:8]}"
    try:
        with psycopg.connect(database_url(), autocommit=True) as conn:
            # Append v2 and move the active pointer atomically (the partial unique index forbids two
            # actives), mirroring how an operator would author a new version.
            conn.execute("UPDATE prompt_versions SET is_active = false WHERE key = 'rules'")
            conn.execute(
                "INSERT INTO prompt_versions (key, version, content, is_active, note) "
                "VALUES ('rules', 2, %s, true, 'test override')",
                (marker,),
            )
        store = PromptStore(reader=read_active_prompts_from_db, ttl_seconds=60.0)
        await store.warm()
        assert store.get("rules") == marker
    finally:
        with psycopg.connect(database_url(), autocommit=True) as conn:
            conn.execute("DELETE FROM prompt_versions WHERE key = 'rules' AND version = 2")
            conn.execute(
                "UPDATE prompt_versions SET is_active = true WHERE key = 'rules' AND version = 1"
            )
        await dispose_engine()


@pytest.mark.integration
def test_prompt_versions_table_is_deny_by_default_on_live_stack() -> None:
    """``prompt_versions`` has RLS enabled with NO policy (deny-by-default), like feature_flags."""
    from tests.rls_helpers import policies_by_table, rls_status

    with psycopg.connect(database_url(), autocommit=True) as conn:
        status = rls_status(conn)
        policies = policies_by_table(conn)
    assert status.get("prompt_versions") is True, "prompt_versions must have RLS enabled"
    assert not policies.get("prompt_versions"), "prompt_versions must have NO policy (deny-all)"


@pytest.mark.integration
def test_authenticated_and_anon_have_no_privileges_on_prompt_versions() -> None:
    """Neither ``authenticated`` nor ``anon`` holds ANY table privilege — reads/writes server-only.

    SECURITY: ``prompt_versions`` is GLOBAL operator config, so a logged-in user must never be able
    to read or rewrite the prompts (which drive every generation) via Supabase's PostgREST.
    """
    from tests.rls_helpers import has_table_privilege

    with psycopg.connect(database_url(), autocommit=True) as conn:
        held = [
            f"{role}:{priv}"
            for role in ("authenticated", "anon")
            for priv in ("SELECT", "INSERT", "UPDATE", "DELETE")
            if has_table_privilege(conn, role, "prompt_versions", priv)
        ]
    assert not held, f"authenticated/anon unexpectedly hold privileges on prompt_versions: {held}"


@pytest.mark.integration
def test_authenticated_role_cannot_read_or_write_prompt_versions() -> None:
    """A real ``authenticated`` session is denied at runtime (not just by the grant catalog)."""
    from tests.rls_helpers import acting_as

    uid = uuid.uuid4()
    with acting_as(uid) as conn, pytest.raises(psycopg.errors.InsufficientPrivilege):
        conn.execute("SELECT content FROM prompt_versions")
    with acting_as(uid) as conn, pytest.raises(psycopg.errors.InsufficientPrivilege):
        conn.execute(
            "INSERT INTO prompt_versions (key, version, content) VALUES ('rules', 999, 'hacked')"
        )
