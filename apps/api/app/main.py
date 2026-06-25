"""FastAPI application entrypoint.

Exposes a minimal ``GET /health`` liveness probe. The full HTTP surface
(routers, auth, quota, OTel wiring) lands in later Phase 1 tasks.

When ``LLM_PROVIDER=fake`` a tiny **test-only** router (:mod:`app.testing`) is mounted so the
E2E suite can drive the LLM seam over HTTP and assert zero real LLM calls. It is never mounted
for a real provider, so it cannot appear in dev/staging/prod.
"""

from __future__ import annotations

import os

from fastapi import FastAPI


def _llm_provider() -> str:
    """The configured LLM provider name (``LLM_PROVIDER`` env, default ``groq``)."""
    return os.getenv("LLM_PROVIDER", "groq").strip().lower()


def create_app() -> FastAPI:
    """Build the FastAPI app, mounting test-only routes only under ``LLM_PROVIDER=fake``."""
    application = FastAPI(title="Lengua API")

    @application.get("/health")
    def health() -> dict[str, str]:
        """Liveness probe used by Cloud Run and CI smoke checks."""
        return {"status": "ok"}

    if _llm_provider() == "fake":
        # Imported lazily so the test-only module is never loaded for a real provider.
        from app.testing import router as testing_router

        application.include_router(testing_router)

    return application


app = create_app()
