"""Feature flags — a typed accessor over env defaults overlaid by a small DB table (task 6.9).

Why this exists: to ship a risky/new feature **dark** (off in prod) and be able to flip it on — or
off during an incident — **without a redeploy or a store update**. Each known flag resolves from two
layers, highest-priority last:

1. an **env default** (``FEATURE_*``; **off** unless explicitly set), overlaid by
2. a row in the global ``feature_flags`` table (``name``/``enabled``/``updated_at``) — present row
   wins, so an operator can toggle a flag in prod by writing one row.

The table snapshot is cached in-process for :data:`~app.settings.Settings.feature_flag_ttl_seconds`
(``FEATURE_FLAG_TTL_SECONDS``, default ~30s), so a table change is picked up within the TTL with
**no Cloud Run revision change** — that is what makes 6.9.3 (toggle-without-redeploy) possible. The
clock is **injectable** (default :func:`time.monotonic`) so the TTL refresh is deterministic in
tests, exactly like :mod:`app.ratelimit` / :mod:`app.discover_cache`.

**Security — ``feature_flags`` is GLOBAL operator config, not user data.** The table is
``REVOKE``\\d from ``authenticated``/``anon`` and under deny-by-default RLS (Alembic 0005 / the
canonical Supabase SQL), so a logged-in user can never enable their own flags via PostgREST. The
backend reads it on a **privileged, RLS-bypassing** app connection (the connecting ``postgres`` /
owner role, same role family as :func:`app.deps.get_usage_db`) and exposes only the resolved
**public** map over the ``GET /feature-flags`` API endpoint — clients never read the table directly.
Writes are admin/service-role only.

**Fail-safe.** If the table can't be read (DB down/unset, table missing), the accessor falls back to
the env defaults (no overrides) — i.e. a gated feature stays at its env default (off for the dark
ones). A flag system must never take the app down, and "can't confirm it's on ⇒ treat as off" is the
safe direction for a feature that ships dark.

**Distributed note (Phase 6).** The cache is per-process, like the rate limiter / discover cache; on
a multi-instance deploy each replica refreshes independently within the same TTL, so a toggle is
visible everywhere within ~one TTL. No shared store is needed for a tiny, eventually-consistent flag
read.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from functools import lru_cache
from typing import Annotated

from fastapi import Depends, HTTPException, status
from sqlalchemy import text

from app.db.session import get_sessionmaker
from app.settings import get_settings

logger = logging.getLogger(__name__)

#: Env strings that mean "on" (case/space-insensitive). Anything else — including unset — is off.
_TRUTHY = frozenset({"1", "true", "yes", "on", "t", "y"})

#: Floor for the in-process cache TTL. ``GET /feature-flags`` is public/unauthenticated; a TTL of 0
#: (or negative) would turn it into one ``feature_flags`` DB query *per request* — a
#: config foot-gun an anonymous caller could amplify into DB load. Any non-positive
#: ``FEATURE_FLAG_TTL_SECONDS`` is clamped up to this floor, so the table is read at most ~once/sec.
MIN_TTL_SECONDS = 1.0


def parse_bool(value: str | None) -> bool:
    """Parse an env flag value to a bool. Off by default: ``None`` / unrecognised ⇒ ``False``."""
    return value is not None and value.strip().lower() in _TRUTHY


@dataclass(frozen=True)
class FlagSpec:
    """The typed description of one known feature flag — the single place a flag is declared.

    ``name`` is the stable key used both in the ``feature_flags`` table and the public API map;
    ``env_var`` is the process-env variable holding its default (off unless set to a truthy value);
    ``description`` documents what the flag gates.
    """

    name: str
    env_var: str
    description: str


# ── The flag registry — the ONE typed place known flags are declared (6.9.1) ──────────────────────

#: Experimental "word of the day" surface — a genuinely new, not-yet-finished feature wrapped so it
#: ships **dark** (off by default in every environment). Flipping it on exposes the guarded
#: ``GET /experimental/word-of-the-day`` route + lets the web reveal its UI (task 6.9.2).
WORD_OF_THE_DAY = FlagSpec(
    name="word_of_the_day",
    env_var="FEATURE_WORD_OF_THE_DAY",
    description="Experimental 'word of the day' surface; ships dark (off by default).",
)

#: Every known flag (extend here — one typed place). Resolution treats an unknown name as off.
KNOWN_FLAGS: tuple[FlagSpec, ...] = (WORD_OF_THE_DAY,)

#: The subset whose resolved state is safe to expose to the web via ``GET /feature-flags``. Listing
#: public flags **explicitly** (rather than exposing all of ``KNOWN_FLAGS``) keeps the endpoint a
#: deny-by-default allow-list: a future server-only/ops flag is simply omitted here and never leaks.
PUBLIC_FLAGS: tuple[FlagSpec, ...] = (WORD_OF_THE_DAY,)


_SELECT_FLAGS = text("select name, enabled from feature_flags")


async def read_flags_from_db() -> dict[str, bool]:
    """Read the ``feature_flags`` overrides as ``{name: enabled}`` on a privileged app session.

    Opens its **own** plain session from the sessionmaker (the connecting ``postgres``/owner role,
    which bypasses the table's deny-by-default RLS) — never the per-request RLS session, which runs
    as ``authenticated`` and is denied. Returns ``{}`` on any failure (DB unreachable/unset, table
    absent) so flag resolution degrades to the env defaults rather than erroring — a feature gate
    must never take the app down (see the module fail-safe note).
    """
    try:
        async with get_sessionmaker()() as session:
            result = await session.execute(_SELECT_FLAGS)
            return {str(m["name"]): bool(m["enabled"]) for m in result.mappings()}
    except Exception:  # noqa: BLE001 — fail safe to env defaults; a flag read must never 500
        logger.warning(
            "feature_flags table read failed; falling back to env defaults", exc_info=True
        )
        return {}


class FeatureFlags:
    """Resolve known flags from env defaults overlaid by the cached ``feature_flags`` table.

    The table snapshot is fetched through ``reader`` and cached for ``ttl_seconds`` (floored at
    :data:`MIN_TTL_SECONDS` so the public endpoint can't be turned into a per-request DB query)
    against an injectable ``clock``; ``env`` is the source of the per-flag env defaults (default the
    process environment). All three are injectable so tests are fully deterministic (fake reader +
    fake clock + a dict env) and so the production singleton can read the real DB + real env.
    """

    def __init__(
        self,
        *,
        reader: Callable[[], Awaitable[dict[str, bool]]],
        ttl_seconds: float,
        clock: Callable[[], float] = time.monotonic,
        env: Mapping[str, str] | None = None,
    ) -> None:
        self._reader = reader
        # Clamp non-positive TTLs up to the floor so the unauthenticated /feature-flags endpoint
        # can never become a DB-query-per-request (see MIN_TTL_SECONDS).
        self._ttl = max(float(ttl_seconds), MIN_TTL_SECONDS)
        self._clock = clock
        self._env: Mapping[str, str] = os.environ if env is None else env
        self._overrides: dict[str, bool] | None = None
        self._fetched_at = 0.0
        # Dedupes a refresh storm: concurrent requests that arrive with an expired cache make ONE
        # table read, not N. (The process singleton lives in one event loop; tests inject their own
        # instance per test, mirroring get_rate_limiter / get_llm_limiter.)
        self._lock = asyncio.Lock()

    async def _table_overrides(self) -> dict[str, bool]:
        """Return the cached table snapshot, refreshing it when older than the TTL."""
        if not self._expired():
            assert self._overrides is not None  # _expired() is False only once a snapshot exists
            return self._overrides
        async with self._lock:
            # Re-check under the lock: another coroutine may have refreshed while we waited.
            if self._expired():
                self._overrides = await self._reader()
                self._fetched_at = self._clock()
            assert self._overrides is not None
            return self._overrides

    def _expired(self) -> bool:
        """True when there is no snapshot yet, or the cached one is older than the TTL."""
        if self._overrides is None:
            return True
        return (self._clock() - self._fetched_at) >= self._ttl

    def _env_default(self, flag: FlagSpec) -> bool:
        """The flag's env-derived default (off unless its ``FEATURE_*`` var is truthy)."""
        return parse_bool(self._env.get(flag.env_var))

    async def is_enabled(self, flag: FlagSpec) -> bool:
        """Resolve one flag: a ``feature_flags`` row (if present) overrides the env default."""
        overrides = await self._table_overrides()
        if flag.name in overrides:
            return overrides[flag.name]
        return self._env_default(flag)

    async def public_map(self) -> dict[str, bool]:
        """The resolved state of every **public** flag — the body of ``GET /feature-flags``.

        Only flags in :data:`PUBLIC_FLAGS` are included (deny-by-default allow-list), and only the
        boolean state is exposed — never the env-var name or any secret.
        """
        overrides = await self._table_overrides()
        return {
            flag.name: overrides.get(flag.name, self._env_default(flag)) for flag in PUBLIC_FLAGS
        }

    def invalidate(self) -> None:
        """Drop the cached snapshot so the next resolution re-reads the table immediately."""
        self._overrides = None
        self._fetched_at = 0.0


@lru_cache(maxsize=1)
def _default_feature_flags() -> FeatureFlags:
    """The process-wide singleton accessor, sized from settings (cached so it survives requests)."""
    return FeatureFlags(
        reader=read_flags_from_db,
        ttl_seconds=get_settings().feature_flag_ttl_seconds,
    )


def get_feature_flags() -> FeatureFlags:
    """FastAPI dependency: the process-wide :class:`FeatureFlags`.

    Returns the shared singleton so the TTL cache survives across requests (a fresh accessor per
    request would re-read the table every time). Tests override this dependency with a fresh
    accessor (fake reader + fake clock) so the global cache can't bleed between tests, mirroring
    ``get_rate_limiter`` / ``get_discover_cache``.
    """
    return _default_feature_flags()


def reset_feature_flags() -> None:
    """Drop the singleton so the next :func:`get_feature_flags` rebuilds it from settings."""
    _default_feature_flags.cache_clear()


def require_flag(flag: FlagSpec) -> Callable[[FeatureFlags], Awaitable[None]]:
    """Build a FastAPI dependency that **404s** unless ``flag`` is enabled (a dark-feature gate).

    A disabled flag makes the guarded route answer ``404 Not Found`` — as if it does not exist — so
    a feature ships truly dark (absent, not merely forbidden). Enabling the flag (env or table)
    exposes it. Construct the dependency **once** at module load (e.g. in the router) so FastAPI's
    per-request dependency cache keys on a stable callable.
    """

    async def _guard(flags: Annotated[FeatureFlags, Depends(get_feature_flags)]) -> None:
        if not await flags.is_enabled(flag):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not Found")

    return _guard
