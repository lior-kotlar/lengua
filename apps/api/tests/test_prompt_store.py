"""DB-backed prompts with versioning — the store, the builders' fallback, and the lockdown (#80).

Layered like the feature-flags suite:

* **Unit (offline)** — the pure ``lengua_core.prompts`` builders' source-hook fallback (code default
  when no source / a source ``None``), and the :class:`~app.prompt_store.PromptStore` accessor: warm
  + synchronous ``get``, the TTL cache + the *change-without-redeploy* refresh (against an injected
  clock), the TTL floor, ``invalidate``, concurrent-warm-reads-once, the whole-map ``snapshot()``
  (torn-assembly guard, #150), and ``_validate_snapshot`` read-time validation (unknown keys and
  empty-string overrides dropped). All use injected fakes, so they need no database.
* **Integration (``@pytest.mark.integration``)** — the *real* DB read path against the seeded
  ``prompt_versions`` table: the seed matches the code defaults, exactly one active version per key,
  a new active version changes what the store resolves (the acceptance criterion), and the SECURITY
  proof that the global table is locked down (``authenticated``/``anon`` cannot read or write it).
  These auto-skip when the Supabase stack is unreachable (see ``tests/conftest``).
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Callable

import psycopg
import pytest

import app.prompt_store as ps
from app.prompt_store import (
    MIN_TTL_SECONDS,
    PromptStore,
    get_prompt_store,
    read_active_prompts_from_db,
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
) -> PromptStore:
    """A :class:`PromptStore` whose active layer is a fixed dict and whose clock is frozen at 0."""
    snapshot = dict(active or {})

    async def reader() -> dict[str, str]:
        return dict(snapshot)

    return PromptStore(
        reader=reader,
        ttl_seconds=ttl,
        clock=clock or (lambda: 0.0),
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


# ── snapshot(): the whole-map capture that prevents the torn-assembly race (#150) ────────────────


@pytest.mark.asyncio
async def test_snapshot_is_empty_before_warm() -> None:
    """A cold store's ``snapshot`` is an empty map (⇒ every fragment uses its code default)."""
    store = make_store(active={prompts.KEY_RULES: "X"})
    assert dict(store.snapshot()) == {}


@pytest.mark.asyncio
async def test_snapshot_returns_the_whole_active_map_and_is_read_only() -> None:
    """After ``warm``, ``snapshot`` returns the whole active map and it cannot be mutated."""
    store = make_store(active={prompts.KEY_RULES: "R", prompts.KEY_OUTPUT_FORMAT: "O"})
    await store.warm()
    snap = store.snapshot()
    assert dict(snap) == {prompts.KEY_RULES: "R", prompts.KEY_OUTPUT_FORMAT: "O"}
    with pytest.raises(TypeError):  # a read-only MappingProxyType — a build can't mutate the cache
        snap[prompts.KEY_RULES] = "MUTATED"  # type: ignore[index]


@pytest.mark.asyncio
async def test_install_wires_snapshot_so_a_build_reads_one_coherent_version() -> None:
    """A build captures the whole snapshot once; a concurrent warm can't tear it across versions.

    Reproduces the #150 race deterministically: with the store installed, we begin a build (capture
    the snapshot), then swap the store's active snapshot to v2 *before* the build resolves its
    remaining fragments — the build must still see v1 throughout, not a v1/v2 mix.
    """
    reader_state = {prompts.KEY_RULES: "RULES v1", prompts.KEY_OUTPUT_FORMAT: "OUTPUT v1"}
    now = {"t": 0.0}

    async def reader() -> dict[str, str]:
        return dict(reader_state)

    store = PromptStore(reader=reader, ttl_seconds=60.0, clock=lambda: now["t"])
    await store.warm()
    store.install()
    try:
        # A build captures the coherent snapshot once (what ``system_instruction`` does internally).
        captured = prompts._capture_overrides()
        # A concurrent warm now swaps in v2 (new active versions land + TTL expires).
        reader_state[prompts.KEY_RULES] = "RULES v2"
        reader_state[prompts.KEY_OUTPUT_FORMAT] = "OUTPUT v2"
        now["t"] = 999.0
        await store.warm()
        # The in-flight build still resolves every fragment from its v1 capture — no torn mix.
        assert prompts.resolve_fragment(prompts.KEY_RULES, captured) == "RULES v1"
        assert prompts.resolve_fragment(prompts.KEY_OUTPUT_FORMAT, captured) == "OUTPUT v1"
        # A *fresh* build (new capture) now sees v2 — the swap did take effect for later requests.
        fresh = prompts._capture_overrides()
        assert prompts.resolve_fragment(prompts.KEY_RULES, fresh) == "RULES v2"
    finally:
        prompts.set_prompt_source(None)


# ── read_active_prompts_from_db (stubbed sessionmaker — the DB seam, offline) ─────────────────────


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


# ── Read-time validation: drop unknown keys + empty overrides (#150) ─────────────────────────────


@pytest.mark.asyncio
async def test_read_active_prompts_drops_unknown_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    """A row whose key isn't in ``PROMPT_KEYS`` is dropped (it can never resolve to a fragment)."""
    rows: list[dict[str, object]] = [
        {"key": prompts.KEY_RULES, "content": "R"},
        {"key": "bogus_key", "content": "ignored"},
    ]
    monkeypatch.setattr(ps, "get_sessionmaker", lambda: lambda: _FakeSession(rows))
    assert await read_active_prompts_from_db() == {prompts.KEY_RULES: "R"}


@pytest.mark.asyncio
async def test_read_active_prompts_drops_empty_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    """An empty override is dropped so it can't silently blank a fragment (e.g. output_format)."""
    rows: list[dict[str, object]] = [
        {"key": prompts.KEY_OUTPUT_FORMAT, "content": ""},
        {"key": prompts.KEY_RULES, "content": "R"},
    ]
    monkeypatch.setattr(ps, "get_sessionmaker", lambda: lambda: _FakeSession(rows))
    active = await read_active_prompts_from_db()
    assert active == {prompts.KEY_RULES: "R"}  # the empty output_format is gone
    # And through the builder, the blanked key falls back to its full code default.
    store = make_store(active=active)
    await store.warm()
    store.install()
    try:
        assert prompts.system_instruction("Spanish").endswith(
            prompts.OUTPUT_FORMAT.format(language="Spanish")
        )
    finally:
        prompts.set_prompt_source(None)


def test_validate_snapshot_keeps_valid_overrides() -> None:
    """The validator passes through known, non-empty overrides verbatim."""
    raw = {prompts.KEY_RULES: "R", prompts.KEY_LEVEL_INSTRUCTION: "L {level}"}
    assert ps._validate_snapshot(raw) == raw


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
@pytest.mark.asyncio
async def test_db_override_reaches_the_http_generation_system_instruction() -> None:
    """End-to-end wiring proof (#150 A1.c): a DB override reaches a real HTTP generation's prompt.

    A wiring regression (``create_app`` not installing the store, ``run_provider`` not warming it,
    the builder not reading the snapshot) would be invisible today because the autouse offline-store
    fixture installs an **empty** store for every test. Here we deliberately **override** that
    fixture with an in-memory store carrying a distinctive ``generation_instruction`` override, boot
    the real app, and drive a ``POST /generate`` through it. A spy provider assembles the *real*
    ``system_instruction`` (the exact call the production providers make in their worker thread) and
    records it; we assert the override text is present — proving install → warm → snapshot-capture →
    render all fired through the HTTP path.

    Uses an **in-memory** reader (not the DB) so the generation-path warm never opens the shared
    process-wide engine on this test's loop (the cross-loop leak the offline fixture guards). It's
    still marked ``integration`` because the route needs Postgres for the seeded profile + language.
    """
    import uuid as _uuid
    from collections.abc import AsyncIterator

    from httpx import ASGITransport, AsyncClient
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

    from app.db.session import UsageSession, async_dsn, dispose_engine
    from app.deps import get_db, get_llm_provider, get_usage_db
    from app.llm_runner import LLMConcurrencyLimiter, get_llm_limiter
    from app.main import create_app
    from app.ratelimit import InProcessRateLimiter, RateLimiter, get_rate_limiter
    from lengua_core.llm.base import LLMProvider
    from lengua_core.llm.fake import FakeLLM
    from lengua_core.models import GeneratedCard
    from scripts.seed_dev_user import DEV_USER_ID, seed_dev_user
    from tests.auth_helpers import authenticate_as

    marker = f"DB-OVERRIDE-{_uuid.uuid4().hex[:8]}"
    captured: dict[str, str] = {}

    class _SpyLLM:
        """A provider that assembles the *real* system instruction, records it, then delegates.

        Wraps (rather than subclasses) :class:`FakeLLM` — ``FakeLLM`` lives in the mypy-excluded
        ``lengua_core`` so it types as ``Any`` — and calls ``prompts.system_instruction`` exactly
        as the production providers do inside their worker thread, so ``captured["system"]`` is the
        real assembled prompt the DB override flowed into.
        """

        def __init__(self) -> None:
            self._delegate = FakeLLM()

        def generate_cards(
            self,
            words: list[str],
            language: str,
            vowelized: bool = False,
            level_band: str | None = None,
        ) -> list[GeneratedCard]:
            captured["system"] = prompts.system_instruction(
                language, vowelized=vowelized, level=level_band
            )
            cards: list[GeneratedCard] = self._delegate.generate_cards(
                words, language, vowelized, level_band
            )
            return cards

        def suggest_new_words(
            self,
            language: str,
            level_band: str,
            known_words: list[str],
            count: int = 5,
            topic: str | None = None,
        ) -> list[str]:
            words: list[str] = self._delegate.suggest_new_words(
                language, level_band, known_words, count, topic
            )
            return words

        def explain_word(self, word: str, sentence: str, translation: str, language: str) -> str:
            note: str = self._delegate.explain_word(word, sentence, translation, language)
            return note

    async def _override_reader() -> dict[str, str]:
        # A non-empty active set: override the generation_instruction with our marker text.
        return {prompts.KEY_GENERATION_INSTRUCTION: f"{marker} — teach {{language}}."}

    await dispose_engine()  # rebuild the engine on THIS test's loop (route needs the real DB)
    seed_dev_user()

    # Override the autouse offline (empty) store with our non-empty in-memory store, and install it
    # as the prompt source. ``create_app`` re-installs whatever ``get_prompt_store`` returns, so the
    # override store is what the generation path warms + reads. The autouse fixture's ``reset`` (run
    # after this test) tears it back down.
    store = PromptStore(reader=_override_reader, ttl_seconds=60.0)
    ps.set_prompt_store(store)
    store.install()

    engine = create_async_engine(async_dsn(database_url()))
    conn = await engine.connect()
    trans = await conn.begin()
    session = AsyncSession(
        bind=conn, expire_on_commit=False, join_transaction_mode="create_savepoint"
    )
    try:
        app = create_app()

        async def _override_get_db() -> AsyncIterator[AsyncSession]:
            yield session

        async def _override_get_usage_db() -> AsyncIterator[UsageSession]:
            yield UsageSession(session)

        def _override_provider() -> LLMProvider:
            return _SpyLLM()

        test_rate_limiter = InProcessRateLimiter(limit=1_000_000)
        test_llm_limiter = LLMConcurrencyLimiter(max_concurrency=4)

        def _override_rate_limiter() -> RateLimiter:
            return test_rate_limiter

        def _override_llm_limiter() -> LLMConcurrencyLimiter:
            return test_llm_limiter

        app.dependency_overrides[get_db] = _override_get_db
        app.dependency_overrides[get_usage_db] = _override_get_usage_db
        app.dependency_overrides[get_llm_provider] = _override_provider
        app.dependency_overrides[get_rate_limiter] = _override_rate_limiter
        app.dependency_overrides[get_llm_limiter] = _override_llm_limiter
        authenticate_as(app, _uuid.UUID(DEV_USER_ID))
        FakeLLM.reset_call_count()

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            lang = await client.post("/languages", json={"name": "Spanish", "code": "es"})
            assert lang.status_code == 200, lang.text
            language_id = int(lang.json()["id"])
            resp = await client.post(
                "/generate", json={"language_id": language_id, "words": ["hola"]}
            )
            assert resp.status_code == 200, resp.text
        app.dependency_overrides.clear()
    finally:
        await session.close()
        if trans.is_active:
            await trans.rollback()
        await conn.close()
        await engine.dispose()
        await dispose_engine()

    # The spy assembled the real system instruction and it carries the DB override — the whole
    # install → warm → snapshot → render chain fired through the live HTTP generation path.
    assert "system" in captured, "the spy provider's generate_cards was never called"
    assert marker in captured["system"]
    assert "teach Spanish." in captured["system"]  # the {language} placeholder was interpolated


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
