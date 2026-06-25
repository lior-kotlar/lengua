"""FastAPI request-scoped dependencies (task 1.5.1).

- :func:`get_db` — the async SQLAlchemy session (re-exported from :mod:`app.db.session` so routers
  have a single dependency-import surface).
- :func:`current_user` — the authenticated user id. Until Phase 2 wires Supabase-JWT auth this is
  a fixed placeholder: the seeded dev user (:data:`DEV_USER_ID`). It MUST equal
  ``scripts.seed_dev_user.DEV_USER_ID`` (and ``tests.factories.DEMO_USER_ID``) so FK-bound inserts
  resolve against the seeded ``profiles`` row; ``tests/api/test_deps.py`` guards the match.
- :func:`get_llm_provider` — the active LLM provider behind the ``lengua_core.llm`` seam, selected
  by ``LLM_PROVIDER`` (Groq by default). Overridden with the deterministic ``FakeLLM`` in tests.
"""

from __future__ import annotations

import uuid

from app.db.session import get_db
from lengua_core.llm import LLMProvider, get_provider

__all__ = ["DEV_USER_ID", "current_user", "get_db", "get_llm_provider"]

# The fixed placeholder identity until Phase 2 JWT. See the module docstring for the invariant.
DEV_USER_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")


async def current_user() -> uuid.UUID:
    """Return the authenticated user id (the seeded dev user until Phase 2 JWT auth)."""
    return DEV_USER_ID


def get_llm_provider() -> LLMProvider:
    """Return the active LLM provider; tests override this with ``FakeLLM``."""
    return get_provider()
