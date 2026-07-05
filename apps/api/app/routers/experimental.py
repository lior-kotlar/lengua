"""Experimental, flag-gated surfaces that ship DARK (task 6.9.2).

These are genuinely new / unfinished features wrapped behind a feature flag that defaults **off** in
every environment, so they are present in the code but **unreachable** in prod until an operator
flips the flag — and, because the flag resolves from the ``feature_flags`` table within
``FEATURE_FLAG_TTL_SECONDS``, **without a redeploy** (task 6.9.3).

**Hidden from the OpenAPI contract.** Each route sets ``include_in_schema=False`` so the dark
surface stays out of the public ``openapi.json`` (and thus out of the generated
``packages/api-types`` TypeScript client) while the flag is off — the contract advertises only
reachable endpoints. Runtime behaviour is unchanged: the route still 404s until its flag is flipped
on, then serves normally. When a feature graduates out of "dark", drop this flag and remove
``include_in_schema=False`` so it re-enters the contract.

While the flag is off the route answers ``404 Not Found`` (via
:func:`app.feature_flags.require_flag`) — exactly as if it did not exist — so the feature is
genuinely dark, not merely forbidden. The flag
must be on for the handler to run.

**Auth.** Like every other domain route, these still require a verified JWT: ``get_current_user`` is
listed as the **first** route dependency, so a missing/invalid token is rejected with ``401`` before
the flag gate runs (an unauthenticated probe can't even tell whether the flag is on).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.deps import get_current_user
from app.feature_flags import WORD_OF_THE_DAY, require_flag
from app.schemas.feature_flags import WordOfTheDayOut

router = APIRouter(prefix="/experimental", tags=["experimental"])

# Built once at import so FastAPI's per-request dependency cache keys on a stable callable.
_require_word_of_the_day = require_flag(WORD_OF_THE_DAY)


@router.get(
    "/word-of-the-day",
    response_model=WordOfTheDayOut,
    # Kept out of the public OpenAPI contract while it ships dark (the flag defaults off); runtime
    # behaviour is unchanged — still 404 until the flag is flipped on. See the module docstring.
    include_in_schema=False,
    # Order matters: auth FIRST (401 on a missing token), THEN the flag gate (404 when off). FastAPI
    # solves route-level dependencies in listed order, before any handler body runs.
    dependencies=[Depends(get_current_user), Depends(_require_word_of_the_day)],
)
async def word_of_the_day() -> WordOfTheDayOut:
    """Experimental 'word of the day' — only reachable when the ``word_of_the_day`` flag is on."""
    return WordOfTheDayOut(
        word="lengua",
        translation="tongue / language",
        note="Experimental preview — the full 'word of the day' feature is under construction.",
    )
