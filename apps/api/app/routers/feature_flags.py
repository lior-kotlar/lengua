"""Public ``GET /feature-flags`` — the resolved PUBLIC feature-flag map (task 6.9.1).

Unauthenticated and secret-free: it returns only the boolean state of the flags in
:data:`app.feature_flags.PUBLIC_FLAGS` (an explicit allow-list), resolved server-side from the env
defaults overlaid by the global ``feature_flags`` table (cached for ``FEATURE_FLAG_TTL_SECONDS``).
The web reads this to gate dark UI (the typed hook ``apps/web/src/lib/feature-flags.ts``).

It exposes no env-var names, no server-only flags, and no user data, so — like ``/health`` /
``/ready`` — it is deliberately **public** (no JWT). Clients never read the ``feature_flags`` table
directly (it is locked down to the server); this endpoint is the only path flag state reaches the
browser.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from app.feature_flags import FeatureFlags, get_feature_flags

router = APIRouter(tags=["feature-flags"])


@router.get("/feature-flags", response_model=dict[str, bool])
async def read_feature_flags(
    flags: Annotated[FeatureFlags, Depends(get_feature_flags)],
) -> dict[str, bool]:
    """Return the resolved PUBLIC feature-flag map (``{name: enabled}``, no secrets)."""
    return await flags.public_map()
