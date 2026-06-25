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

from app.observability import configure_observability
from app.routers import (
    cards,
    discover,
    explain,
    generate,
    languages,
    proficiency,
    review,
    settings,
)


def _llm_provider() -> str:
    """The configured LLM provider name (``LLM_PROVIDER`` env, default ``groq``)."""
    return os.getenv("LLM_PROVIDER", "groq").strip().lower()


def create_app(*, include_test_routes: bool | None = None) -> FastAPI:
    """Build the FastAPI app.

    The test-only router (:mod:`app.testing`) is mounted when ``include_test_routes`` is True or,
    when it is ``None`` (the default), when ``LLM_PROVIDER=fake`` — so the E2E stack still gets
    the ``/__test__/*`` routes while a real provider never does. Pass ``include_test_routes=False``
    to build the canonical **public** schema (used by ``scripts/dump_openapi.py`` + the drift
    test) so the committed ``openapi.json`` never depends on the runtime LLM provider.
    """
    application = FastAPI(title="Lengua API")

    # Observability (Phase 1.7): OTel tracing (FastAPI/SQLAlchemy/httpx auto-instrumentation,
    # no-op exporter unless OTEL_EXPORTER_OTLP_ENDPOINT is set) + one structured JSON access-log
    # line per request, with a trace_id for correlation.
    configure_observability(application)

    @application.get("/health")
    def health() -> dict[str, str]:
        """Liveness probe used by Cloud Run and CI smoke checks."""
        return {"status": "ok"}

    # Full-loop routers, all scoped to current_user (the seeded dev user until Phase 2 JWT):
    # languages -> generate -> save -> review, plus discover/explain/proficiency/settings.
    application.include_router(languages.router)
    application.include_router(generate.router)
    application.include_router(cards.router)
    application.include_router(review.router)
    application.include_router(discover.router)
    application.include_router(explain.router)
    application.include_router(proficiency.router)
    application.include_router(settings.router)

    if include_test_routes is None:
        include_test_routes = _llm_provider() == "fake"
    if include_test_routes:
        # Imported lazily so the test-only module is never loaded for a real provider.
        from app.testing import router as testing_router

        application.include_router(testing_router)

    return application


app = create_app()
