"""FastAPI application entrypoint.

Builds the app in :func:`create_app`: a ``GET /health`` liveness probe, OTel + structured-logging
observability, the strict CORS allowlist, every feature router (all scoped to ``current_user``), and
the Phase 3 LLM cost-guard exception handlers — the quota gates (email/rate/daily-cap/global-budget)
plus the concurrency/backoff busy handlers (``ProviderBusy`` from the in-flight cap and a persistent
provider 429/5xx → **503 ``server_busy``**). Auth is enforced per-router via the JWT dependencies in
:mod:`app.deps`.

When ``LLM_PROVIDER=fake`` a tiny **test-only** router (:mod:`app.testing`) is mounted so the
E2E suite can drive the LLM seam over HTTP and assert zero real LLM calls. It is never mounted
for a real provider, so it cannot appear in dev/staging/prod.
"""

from __future__ import annotations

import logging
import os

from fastapi import FastAPI, Response, status
from fastapi.middleware.cors import CORSMiddleware

from app.db.session import check_db_ready
from app.error_tracking import configure_error_tracking
from app.llm_runner import register_llm_handlers
from app.observability import configure_observability
from app.prompt_store import install_prompt_store
from app.quota import register_quota_handlers
from app.routers import (
    account,
    account_deletion,
    cards,
    discover,
    experimental,
    explain,
    feature_flags,
    generate,
    languages,
    me,
    proficiency,
    review,
    settings,
)
from app.security_headers import configure_security_headers
from app.settings import Settings, get_settings

logger = logging.getLogger(__name__)

#: Deployment environments where the RLS-bypassing Supabase service-role key is REQUIRED (the
#: account-deletion path needs it). ``local``/``ci``/``test``/``e2e`` run WITHOUT it by design
#: (FakeLLM + the E2E stack never hard-delete a real auth user), so the boot check is a strict no-op
#: there and only fires for a real deployment.
_SECRET_REQUIRED_ENVS = frozenset({"staging", "prod"})


def _llm_provider() -> str:
    """The configured LLM provider name (``LLM_PROVIDER`` env, default ``groq``)."""
    return os.getenv("LLM_PROVIDER", "groq").strip().lower()


def _check_deployment_secrets(app_settings: Settings) -> None:
    """Log a CRITICAL at boot when a real deployment is missing Supabase admin credentials.

    :class:`app.services.account.AccountDeletionService` fails closed only when a user first calls
    ``DELETE /account``: with an empty ``SUPABASE_SERVICE_ROLE_KEY`` / ``SUPABASE_URL`` a
    misconfigured staging/prod otherwise looks perfectly healthy until that first deletion. This
    surfaces the misconfiguration loudly at startup instead.

    Strictly gated on ``settings.env``: a **no-op** for ``local``/``ci``/``test``/``e2e`` (which run
    without the key by design). It intentionally does NOT crash the app — a boot crash over an
    ops-fixable config gap is a worse failure mode than a loud CRITICAL log (every other route stays
    up; only account deletion is affected until the key is set).
    """
    if app_settings.env.strip().lower() not in _SECRET_REQUIRED_ENVS:
        return
    service_role_key = app_settings.supabase_service_role_key.get_secret_value()
    missing = [
        name
        for name, value in (
            ("SUPABASE_SERVICE_ROLE_KEY", service_role_key),
            ("SUPABASE_URL", app_settings.supabase_url),
        )
        if not value
    ]
    if missing:
        logger.critical(
            "Supabase admin config missing in env=%s: %s unset/empty. Account deletion "
            "(DELETE /account) will fail until this is configured.",
            app_settings.env,
            ", ".join(missing),
        )


def create_app(*, include_test_routes: bool | None = None) -> FastAPI:
    """Build the FastAPI app.

    The test-only router (:mod:`app.testing`) is mounted when ``include_test_routes`` is True or,
    when it is ``None`` (the default), when ``LLM_PROVIDER=fake`` — so the E2E stack still gets
    the ``/__test__/*`` routes while a real provider never does. Pass ``include_test_routes=False``
    to build the canonical **public** schema (used by ``scripts/dump_openapi.py`` + the drift
    test) so the committed ``openapi.json`` never depends on the runtime LLM provider.
    """
    application = FastAPI(title="Lengua API")

    # Boot-time config guard: in a real deployment (staging/prod), a missing Supabase service-role
    # key / URL is a latent failure that only bites the first DELETE /account. Surface it loudly at
    # startup. A strict no-op for local/ci/test/e2e (see _check_deployment_secrets).
    _check_deployment_secrets(get_settings())

    # Observability (Phase 1.7): OTel tracing (FastAPI/SQLAlchemy/httpx auto-instrumentation,
    # no-op exporter unless OTEL_EXPORTER_OTLP_ENDPOINT is set) + one structured JSON access-log
    # line per request, with a trace_id for correlation.
    configure_observability(application)

    # Error tracking (Phase 5.4.1): initialise Sentry ONLY when SENTRY_DSN_API is set (a no-op with
    # zero egress otherwise, like the OTLP exporters). When enabled, the FastAPI integration
    # captures unhandled exceptions, each tagged with the OTel trace_id + the request user_id (bound
    # per request in app.deps.get_current_user) so a Sentry issue links to its Grafana Tempo trace.
    configure_error_tracking(get_settings())

    # Security response headers (finding S17): X-Content-Type-Options / X-Frame-Options /
    # Referrer-Policy / HSTS on every response. Added BEFORE CORS on purpose so CORS stays the
    # outermost layer and its preflight short-circuit is untouched (see app.security_headers).
    configure_security_headers(application)

    # CORS allowlist (Phase 2.3.4): only the configured browser/app origins may make cross-origin
    # requests; an unlisted origin gets no Access-Control-Allow-Origin. Added last so it is the
    # outermost layer (preflight OPTIONS short-circuit before auth/route handling). expose_headers
    # lets the cross-origin SPA read Retry-After on 429/503 so the backoff countdown is exact (S16).
    cors_origins = get_settings().cors_allow_origins
    application.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["Retry-After"],
    )

    @application.get("/health")
    def health() -> dict[str, str]:
        """Liveness probe used by Cloud Run and CI smoke checks."""
        return {"status": "ok"}

    @application.get("/ready")
    async def ready(response: Response) -> dict[str, str]:
        """Readiness probe: ``200 {"status":"ready"}`` when the DB answers, else ``503``.

        Unauthenticated like ``/health``, but where the pure liveness probe does no I/O, ``/ready``
        verifies database connectivity with a lightweight ``SELECT 1`` on a PLAIN (RLS-free) engine
        connection — no JWT, never the ``authenticated`` role (see
        :func:`app.db.session.check_db_ready`). Cloud Run's startup + liveness probes point at
        ``/health`` (so a transient DB blip never *kills* the instance); its **readiness** probe
        points here, so an instance that cannot reach Postgres is pulled from rotation until it
        recovers. Any failure answers ``503``, never a ``500`` (wiring these probes into the Cloud
        Run service config lands in CD, group 6.6).
        """
        if await check_db_ready():
            return {"status": "ready"}
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {"status": "not_ready"}

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
    # Public account-deletion request/confirm (Phase 8, task 8.3.1): intentionally UNauthenticated —
    # the external web deletion path Google Play requires. Ownership is proven by an emailed signed
    # token, not a session (see app/routers/account_deletion.py).
    application.include_router(account_deletion.router)

    # Feature flags (Phase 6.9): the public, secret-free flag map (no JWT) + the experimental
    # flag-gated routes that ship dark (still JWT-protected; 404 until their flag is flipped on).
    application.include_router(feature_flags.router)
    application.include_router(experimental.router)

    # LLM cost guard (Phase 3): map each gate's exception to its contract response — email gate →
    # 403 {"code":"email_unverified"}, rate-limit → 429 {"code":"rate_limited"} (+ Retry-After),
    # daily-cap → 429 {"code":"daily_cap_reached","kind":...}, and the global-budget kill-switch
    # (3.4) → 429 {"code":"daily_limit_reached","message":...}.
    register_quota_handlers(application)
    # Concurrency cap + backoff (Phase 3.5): the in-flight cap's ProviderBusy and a persistent
    # provider 429/5xx (LLMTransientError) both → 503 {"code":"server_busy",...} (+ Retry-After).
    register_llm_handlers(application)

    # DB-backed prompts (GitHub #80): install the process-wide prompt store as the source for the
    # ``lengua_core.prompts`` builders, so generation uses the ACTIVE ``prompt_versions`` (refreshed
    # per-call within the TTL by ``app.llm_runner.run_provider``). No DB is touched here — the store
    # reads lazily and falls back to the in-code defaults when the table is empty/unreachable, so
    # local/CI/E2E (FakeLLM) and a DB-less boot are unaffected.
    install_prompt_store()

    if include_test_routes is None:
        include_test_routes = _llm_provider() == "fake"
    if include_test_routes:
        # Imported lazily so the test-only module is never loaded for a real provider.
        from app.testing import router as testing_router

        application.include_router(testing_router)

    return application


app = create_app()
