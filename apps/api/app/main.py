"""FastAPI application entrypoint.

Builds the app in :func:`create_app`: a ``GET /health`` liveness probe, OTel + structured-logging
observability, the strict CORS allowlist, every feature router (all scoped to ``current_user``), and
the Phase 3 LLM cost-guard exception handlers (the per-user daily-cap gate's ``DailyCapReached`` →
429). Auth is enforced per-router via the JWT dependencies in :mod:`app.deps`.

When ``LLM_PROVIDER=fake`` a tiny **test-only** router (:mod:`app.testing`) is mounted so the
E2E suite can drive the LLM seam over HTTP and assert zero real LLM calls. It is never mounted
for a real provider, so it cannot appear in dev/staging/prod.
"""

from __future__ import annotations

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.observability import configure_observability
from app.quota import register_quota_handlers
from app.routers import (
    account,
    cards,
    discover,
    explain,
    generate,
    languages,
    me,
    proficiency,
    review,
    settings,
)
from app.settings import get_settings


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

    # CORS allowlist (Phase 2.3.4): only the configured browser/app origins may make cross-origin
    # requests; an unlisted origin gets no Access-Control-Allow-Origin. Added last so it is the
    # outermost layer (preflight OPTIONS short-circuit before auth/route handling).
    cors_origins = get_settings().cors_allow_origins
    application.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @application.get("/health")
    def health() -> dict[str, str]:
        """Liveness probe used by Cloud Run and CI smoke checks."""
        return {"status": "ok"}

    # The JWT smoke-protected identity route (everything below is scoped to current_user).
    application.include_router(me.router)

    # Full-loop routers, all scoped to current_user:
    # languages -> generate -> save -> review, plus discover/explain/proficiency/settings.
    application.include_router(languages.router)
    application.include_router(generate.router)
    application.include_router(cards.router)
    application.include_router(review.router)
    application.include_router(discover.router)
    application.include_router(explain.router)
    application.include_router(proficiency.router)
    application.include_router(settings.router)
    # Account lifecycle (export + hard delete), scoped to current_user (task 2.8).
    application.include_router(account.router)

    # LLM cost guard (Phase 3): map the daily-cap gate's DailyCapReached to a 429 with the
    # contract body {"code": "daily_cap_reached", "kind": ...}.
    register_quota_handlers(application)

    if include_test_routes is None:
        include_test_routes = _llm_provider() == "fake"
    if include_test_routes:
        # Imported lazily so the test-only module is never loaded for a real provider.
        from app.testing import router as testing_router

        application.include_router(testing_router)

    return application


app = create_app()
