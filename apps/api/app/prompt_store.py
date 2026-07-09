"""DB-backed LLM prompts with versioning — the runtime store + fallback (GitHub #80).

Why this exists: to tweak an LLM prompt in **production without a code change + redeploy**, keep a
full history of every wording tried, and be able to roll back to (or pin) an older version. The
prompt fragments live in the append-only ``prompt_versions`` table (one **active** version per
``key``); this module resolves the active set on the server, caches it with a TTL, and feeds it to
the pure prompt builders in :mod:`lengua_core.prompts`.

Layered exactly like :mod:`app.feature_flags` (the other global-operator-config table):

* **Server-only, locked down.** ``prompt_versions`` is ``REVOKE``\\d from ``authenticated``/``anon``
  and under deny-by-default RLS (Alembic 0007 / the canonical Supabase SQL), so a logged-in user can
  never read or rewrite the prompts via PostgREST. The store reads it on a **privileged,
  RLS-bypassing** app session (the connecting ``postgres``/owner role, same family as
  :func:`app.deps.get_usage_db`). Prompts are global config, not user data — nothing here is
  per-user or exposed to clients.
* **TTL cache.** The active snapshot is cached for
  :data:`~app.settings.Settings.prompt_cache_ttl_seconds` against an injectable clock, so an
  operator who appends a new active version sees generation change within one TTL window — **no
  redeploy** — and the DB is read at most ~once/TTL, not once per generation.
* **Fallback to the in-code defaults.** If the table is empty/unreachable, or for the paths that
  never install this store (the **legacy Streamlit app**, and dev/CI/E2E with ``FakeLLM``), the
  builders fall back to the code constants in :mod:`lengua_core.prompts`. That keeps "legacy
  Streamlit runnable" and the "zero real-LLM-call E2E" contract intact.

**The sync/async seam.** The builders (``system_instruction`` / ``suggestion_instruction``) are
**synchronous** and run **inside the blocking provider call**, which the app offloads to a worker
thread (:mod:`app.llm_runner`). They therefore can't ``await`` a DB read. So this store splits into:

* an **async refresh** (:meth:`PromptStore.warm`) run on the event loop *before* the provider call
  is dispatched (see :func:`warm_prompt_store`, wired into ``run_provider``), and
* a **synchronous** :meth:`PromptStore.get` the builders call from the worker thread, which only
  reads the already-materialised in-memory snapshot (no I/O). :meth:`PromptStore.install` registers
  it as the :func:`lengua_core.prompts.set_prompt_source` hook.

**"Always use the latest version" + the -1 sentinel.** :meth:`resolve` takes an optional
``version``: ``-1`` (the default) resolves to the current **active** version for the key (via the
cached snapshot); a positive ``version`` **pins** that exact version (reproducibility / debugging /
A/B) by reading it straight from the DB. The default generation path always uses the active version.

**Fail-safe.** A DB read failure yields an empty snapshot, so every fragment falls back to its code
default — a prompt read must never take generation down.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from functools import lru_cache

from sqlalchemy import text

from app.db.session import get_sessionmaker
from app.settings import get_settings
from lengua_core import prompts

logger = logging.getLogger(__name__)

#: Sentinel meaning "resolve the current active version" (see :meth:`PromptStore.resolve`).
ACTIVE_VERSION = -1

#: Floor for the in-process cache TTL, mirroring ``app.feature_flags.MIN_TTL_SECONDS``: a
#: non-positive ``PROMPT_CACHE_TTL_SECONDS`` would re-read ``prompt_versions`` on *every* generation
#: (a needless DB query per LLM call), so any non-positive TTL is clamped up to this floor.
MIN_TTL_SECONDS = 1.0

# Read the active content for every key in one round-trip. Only ``is_active`` rows, so exactly one
# row per key (the partial unique index guarantees at most one).
_SELECT_ACTIVE = text("select key, content from prompt_versions where is_active")

# Read one pinned (key, version) row's content — the reproducibility/A-B path.
_SELECT_PINNED = text("select content from prompt_versions where key = :key and version = :version")


async def read_active_prompts_from_db() -> dict[str, str]:
    """Read the ACTIVE prompt content per key as ``{key: content}`` on a privileged app session.

    Opens its **own** plain session from the sessionmaker (the connecting ``postgres``/owner role,
    which bypasses ``prompt_versions``' deny-by-default RLS) — never the per-request RLS session,
    which runs as ``authenticated`` and is denied. Returns ``{}`` on any failure (DB
    unreachable/unset, table absent) so the builders degrade to the in-code defaults rather than
    erroring — a prompt read must never take generation down (see the module fail-safe note).
    """
    try:
        async with get_sessionmaker()() as session:
            result = await session.execute(_SELECT_ACTIVE)
            return {str(m["key"]): str(m["content"]) for m in result.mappings()}
    except Exception:  # noqa: BLE001 — fail safe to code defaults; a prompt read must never 500
        logger.warning(
            "prompt_versions table read failed; falling back to in-code prompt defaults",
            exc_info=True,
        )
        return {}


async def read_pinned_prompt_from_db(key: str, version: int) -> str | None:
    """Read one pinned ``(key, version)`` row's content, or ``None`` if it doesn't exist / on error.

    The reproducibility / A-B path (:meth:`PromptStore.resolve` with a positive ``version``). Uses
    the same privileged session as :func:`read_active_prompts_from_db`; ``None`` means "no such
    pinned version" so the caller falls back to the code default.
    """
    try:
        async with get_sessionmaker()() as session:
            result = await session.execute(_SELECT_PINNED.bindparams(key=key, version=version))
            row = result.first()
            return None if row is None else str(row[0])
    except Exception:  # noqa: BLE001 — fail safe to the code default
        logger.warning(
            "pinned prompt_versions read failed (key=%s version=%s); using code default",
            key,
            version,
            exc_info=True,
        )
        return None


class PromptStore:
    """Resolve prompt fragments from the cached ACTIVE ``prompt_versions``, with a code fallback.

    The active snapshot is fetched through ``reader`` and cached for ``ttl_seconds`` (floored at
    :data:`MIN_TTL_SECONDS`) against an injectable ``clock``. All are injectable so tests are fully
    deterministic (fake reader + fake clock) and the production singleton reads the real DB. A
    ``pinned_reader`` backs the positive-``version`` pin path (defaults to the real DB reader).
    """

    def __init__(
        self,
        *,
        reader: Callable[[], Awaitable[dict[str, str]]],
        ttl_seconds: float,
        clock: Callable[[], float] = time.monotonic,
        pinned_reader: Callable[[str, int], Awaitable[str | None]] | None = None,
    ) -> None:
        self._reader = reader
        self._pinned_reader = pinned_reader or read_pinned_prompt_from_db
        # Clamp non-positive TTLs up to the floor so we never re-read the table on every generation.
        self._ttl = max(float(ttl_seconds), MIN_TTL_SECONDS)
        self._clock = clock
        self._active: dict[str, str] | None = None
        self._fetched_at = 0.0
        # Dedupes a refresh storm: concurrent warms with an expired cache make ONE table read.
        self._lock = asyncio.Lock()

    def _expired(self) -> bool:
        """True when there is no snapshot yet, or the cached one is older than the TTL."""
        if self._active is None:
            return True
        return (self._clock() - self._fetched_at) >= self._ttl

    async def warm(self) -> dict[str, str]:
        """Refresh the active snapshot if the TTL has expired, and return it.

        Called on the event loop *before* the (blocking, threaded) provider call so the synchronous
        :meth:`get` the builders call in the worker thread reads a materialised snapshot. Returns
        the current snapshot (possibly the cached one when still fresh).
        """
        if not self._expired():
            assert self._active is not None  # _expired() is False only once a snapshot exists
            return self._active
        async with self._lock:
            # Re-check under the lock: another coroutine may have refreshed while we waited.
            if self._expired():
                self._active = await self._reader()
                self._fetched_at = self._clock()
            assert self._active is not None
            return self._active

    def get(self, key: str) -> str | None:
        """Synchronously return the ACTIVE content for ``key``, or ``None`` to fall back to code.

        Reads only the in-memory snapshot (no I/O), so it is safe to call from the provider worker
        thread. ``None`` — no snapshot yet, or the key isn't active in the DB — makes the builder
        use its code default. This is the callable installed via
        :func:`lengua_core.prompts.set_prompt_source`.
        """
        active = self._active
        if active is None:
            return None
        return active.get(key)

    async def resolve(self, key: str, version: int = ACTIVE_VERSION) -> str:
        """Resolve ``key`` to its text: the ACTIVE version (``version == -1``) or a pinned positive.

        ``version == ACTIVE_VERSION`` (``-1``, the default) uses the cached active snapshot (warming
        it if needed). A positive ``version`` reads that exact row from the DB (reproducibility /
        debugging / A-B). Either way, a miss (key not active / no such pinned version / DB down)
        falls back to :data:`lengua_core.prompts.CODE_DEFAULTS`.
        """
        default: str = prompts.CODE_DEFAULTS[key]
        if version == ACTIVE_VERSION:
            active = await self.warm()
            resolved = active.get(key)
            return resolved if resolved is not None else default
        pinned = await self._pinned_reader(key, version)
        return pinned if pinned is not None else default

    def install(self) -> None:
        """Register this store's synchronous :meth:`get` as the ``lengua_core.prompts`` source."""
        prompts.set_prompt_source(self.get)

    def invalidate(self) -> None:
        """Drop the cached snapshot so the next :meth:`warm` re-reads the table immediately."""
        self._active = None
        self._fetched_at = 0.0


@lru_cache(maxsize=1)
def _default_prompt_store() -> PromptStore:
    """The process-wide singleton store, sized from settings (cached so the TTL cache is one)."""
    return PromptStore(
        reader=read_active_prompts_from_db,
        ttl_seconds=get_settings().prompt_cache_ttl_seconds,
    )


#: A test-installed store that supersedes the DB-backed singleton. Tests that drive HTTP through the
#: real app (e.g. ``tests/api``) install an in-memory store here so ``warm_prompt_store`` never
#: opens the **shared** process-wide engine/sessionmaker (which would bind it to that test's event
#: loop and leak a connection into the next async test — the same cross-loop hazard the ``dispose``
#: dance guards). ``None`` ⇒ use the DB-backed singleton (production + the DB-integration tests).
_override_store: PromptStore | None = None


def get_prompt_store() -> PromptStore:
    """Return the active :class:`PromptStore`: a test override if installed, else the singleton.

    The singleton's TTL cache survives across calls (a fresh store per call would re-read the table
    every time). Tests may install an in-memory override via :func:`set_prompt_store`.
    """
    if _override_store is not None:
        return _override_store
    return _default_prompt_store()


def set_prompt_store(store: PromptStore | None) -> None:
    """Install (or clear with ``None``) a test store that supersedes the DB-backed singleton.

    A convenience for tests driving the real app over HTTP: an in-memory store keeps
    :func:`warm_prompt_store` off the shared engine (see :data:`_override_store`). Cleared by
    :func:`reset_prompt_store`.
    """
    global _override_store
    _override_store = store


def reset_prompt_store() -> None:
    """Drop the singleton + any test override and clear the installed source hook.

    Rebuilds the singleton from settings on the next :func:`get_prompt_store`, and restores the
    "no store installed → in-code prompt defaults" behaviour — used by tests to avoid a stale
    singleton (or its hook/override) bleeding between them.
    """
    _default_prompt_store.cache_clear()
    set_prompt_store(None)
    prompts.set_prompt_source(None)


async def warm_prompt_store() -> None:
    """Refresh the process-wide store's active snapshot (best-effort; never raises).

    Called on the event loop before each provider call (from ``app.llm_runner.run_provider``) so the
    synchronous builders read a fresh-within-TTL snapshot in the worker thread. Any failure is
    swallowed — the reader already fails safe to ``{}``; this guard covers a store that was never
    installed / an unexpected error, so a prompt refresh can never break a generation request.
    """
    try:
        await get_prompt_store().warm()
    except Exception:  # noqa: BLE001 — a prompt warm must never take generation down
        logger.warning(
            "prompt store warm failed; using last snapshot / code defaults", exc_info=True
        )


def install_prompt_store() -> None:
    """Install the active store as the prompt source (called once from ``create_app``)."""
    get_prompt_store().install()


def install_offline_prompt_store() -> PromptStore:
    """Install an in-memory prompt store (empty active set) as the override + source, and return it.

    For tests that drive the real app over HTTP (``tests/api``): the generation path's
    :func:`warm_prompt_store` then reads this in-memory store instead of opening the **shared**
    process-wide engine/sessionmaker, so it can't bind that engine to the test's event loop and leak
    a connection into the next async test. The empty active set means every fragment resolves to its
    in-code default (unchanged generation behaviour). Cleared by :func:`reset_prompt_store` (the
    autouse fixture runs it around every test).
    """

    async def _empty_reader() -> dict[str, str]:
        return {}

    store = PromptStore(reader=_empty_reader, ttl_seconds=60.0)
    set_prompt_store(store)
    store.install()
    return store
