"""Task 5.5.2 verify: a client ``traceparent`` continues into ONE API→DB→LLM trace.

When a request arrives carrying a W3C ``traceparent`` header (the web client injects a fresh one per
API request — task 5.5.1), the FastAPI auto-instrumentation extracts it (OpenTelemetry's default W3C
``tracecontext`` propagator) so the **server span CONTINUES that trace** instead of starting a new
root. This proves the client→API→DB/LLM leg of the correlation checklist: with one supplied trace
id, the FastAPI server span, the SQLAlchemy statement span (DB leg), and the custom ``llm.call``
span (LLM leg) all share it — a single trace.

``@pytest.mark.integration`` — needs the local Supabase Postgres; auto-skips when the DB is down, so
the GitHub CI gate (Postgres up) is the authoritative check.

The DB statement spans require an OTel-*instrumented* engine: the SQLAlchemy auto-instrumentation
only wraps engines built through the patched ``create_async_engine``, and the shared ``db_session``
fixture captured the unwrapped factory at import time (so its engine emits no statement spans). This
file therefore builds its own engine via the module attribute — the same pattern as
``test_otel_db_spans.py``'s ``languages_client`` — plus the ``FakeLLM`` + quota overrides ``POST
/generate`` needs. The provider is the deterministic ``FakeLLM`` (zero real LLM calls); its
in-process call still emits the ``llm.call`` span (the provider-call signal in dev/CI/E2E — see
``test_otel_httpx_spans.py`` for why there is no outbound httpx span under ``FakeLLM``).

LIVE/owner deferrals (logged in ``planning/outstanding-work.md`` §11): seeing the assembled trace in
Grafana Tempo with a **browser/client span as the root**, and the browser EXPORTING its own client
span to Tempo (a web OTLP SDK), need the Phase-6 staging deploy + Grafana creds. This test proves
the propagation/continuation those build on.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
import sqlalchemy.ext.asyncio as sa_asyncio
from httpx import ASGITransport, AsyncClient
from opentelemetry import trace
from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from sqlalchemy.ext.asyncio import AsyncSession

# Importing app.main runs create_app() -> configure_observability(), which installs the global SDK
# TracerProvider the span_exporter fixture attaches to and wraps create_async_engine.
import app.main  # noqa: F401
from app.db.session import UsageSession, async_dsn
from app.deps import DEV_USER_ID, get_db, get_llm_provider, get_usage_db
from app.llm_observability import LLM_SPAN_NAME
from app.llm_runner import LLMConcurrencyLimiter, get_llm_limiter
from app.main import create_app
from app.ratelimit import InProcessRateLimiter, RateLimiter, get_rate_limiter
from lengua_core.llm.base import LLMProvider
from lengua_core.llm.fake import FakeLLM
from scripts.seed_dev_user import seed_dev_user
from tests.auth_helpers import auth_header, install_test_auth
from tests.conftest import _skip_if_db_unreachable, database_url

# A fixed, well-known W3C trace context (the W3C Trace Context spec's own example ids), standing in
# for what the browser client (task 5.5.1) injects. Sampled (flags ``01``) so the server records it.
SUPPLIED_TRACE_ID_HEX = "4bf92f3577b34da6a3ce929d0e0e4736"
SUPPLIED_SPAN_ID_HEX = "00f067aa0ba902b7"
TRACEPARENT = f"00-{SUPPLIED_TRACE_ID_HEX}-{SUPPLIED_SPAN_ID_HEX}-01"


@pytest_asyncio.fixture
async def trace_client(clean_db: None) -> AsyncIterator[AsyncClient]:
    """ASGI client on an *instrumented* engine + ``FakeLLM`` so a generate emits DB + LLM spans.

    Mirrors ``test_otel_db_spans.py``'s ``languages_client`` (engine built via the module attribute
    so the OTel ``EngineTracer`` attaches → statement spans) plus the provider + quota dependency
    overrides a generate call needs. The session is rolled back at teardown.
    """
    _skip_if_db_unreachable()
    seed_dev_user()  # committed dev profile so current_user's FK-bound inserts resolve

    # Build via the module attribute so the OTel-wrapped create_async_engine attaches the
    # EngineTracer (the path get_engine uses) -> SELECT statement spans are emitted.
    engine = sa_asyncio.create_async_engine(async_dsn(database_url()))
    conn = await engine.connect()
    trans = await conn.begin()
    session = AsyncSession(
        bind=conn, expire_on_commit=False, join_transaction_mode="create_savepoint"
    )

    app = create_app()

    async def _override_get_db() -> AsyncIterator[AsyncSession]:
        yield session

    async def _override_get_usage_db() -> AsyncIterator[UsageSession]:
        yield UsageSession(session)  # cost-guard usage reads/writes on the same rolled-back session

    def _override_provider() -> LLMProvider:
        return FakeLLM()

    # Fresh, effectively-unlimited limiters bound to this test's loop (the process-wide singletons
    # would otherwise span event loops); they don't perturb a single admitted generate call.
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
    install_test_auth(app)  # verify the real bearer token against the test secret
    FakeLLM.reset_call_count()

    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            yield client
    finally:
        app.dependency_overrides.clear()
        await session.close()
        if trans.is_active:
            await trans.rollback()
        await conn.close()
        await engine.dispose()


def _is_descendant(
    span: ReadableSpan, ancestor_span_id: int, by_id: dict[int, ReadableSpan]
) -> bool:
    """True if ``span`` is a (transitive) child of the span with ``ancestor_span_id``."""
    seen: set[int] = set()
    current: ReadableSpan | None = span
    while current is not None and current.parent is not None:
        parent_id = current.parent.span_id
        if parent_id == ancestor_span_id:
            return True
        if parent_id in seen:
            break
        seen.add(parent_id)
        current = by_id.get(parent_id)
    return False


@pytest.mark.integration
@pytest.mark.asyncio
async def test_client_traceparent_continues_into_one_trace(
    trace_client: AsyncClient, span_exporter: InMemorySpanExporter
) -> None:
    headers = auth_header(DEV_USER_ID)
    created = await trace_client.post(
        "/languages", json={"name": "Spanish", "code": "es"}, headers=headers
    )
    assert created.status_code == 200, created.text
    language_id = created.json()["id"]

    # The browser client (task 5.5.1) injects exactly this header on every API request. Clearing
    # first drops the setup spans so only the generate request's spans are asserted.
    span_exporter.clear()
    response = await trace_client.post(
        "/generate",
        json={"language_id": language_id, "words": ["hola"]},
        headers={**headers, "traceparent": TRACEPARENT},
    )
    assert response.status_code == 200, response.text

    expected_trace_id = int(SUPPLIED_TRACE_ID_HEX, 16)
    expected_parent_span_id = int(SUPPLIED_SPAN_ID_HEX, 16)
    spans = span_exporter.get_finished_spans()
    by_id = {s.context.span_id: s for s in spans}

    # 1) The FastAPI server span CONTINUES the supplied client trace (same trace id, parented to the
    #    supplied client span id) rather than starting a fresh root trace.
    server_spans = [
        s for s in spans if s.kind == trace.SpanKind.SERVER and "/generate" in (s.name or "")
    ]
    assert server_spans, f"expected a POST /generate server span; got {[s.name for s in spans]}"
    server_span = server_spans[0]
    assert server_span.context.trace_id == expected_trace_id, (
        "server span did not continue the trace"
    )
    assert server_span.parent is not None
    assert server_span.parent.span_id == expected_parent_span_id, (
        "server span is not parented under the supplied client span id"
    )

    # 2) The SQLAlchemy statement span (DB leg) shares the supplied trace id and nests under the
    #    server span — proving client→API→DB is one trace.
    db_spans = [
        s
        for s in spans
        if (s.name or "").upper().startswith(("SELECT", "INSERT", "UPDATE"))
        and s.context.trace_id == expected_trace_id
        and _is_descendant(s, server_span.context.span_id, by_id)
    ]
    assert db_spans, (
        f"expected a DB statement span in the continued trace; got {[s.name for s in spans]}"
    )

    # 3) The custom llm.call span (LLM leg) shares the supplied trace id and nests under the server
    #    span — proving client→API→LLM is the same one trace.
    llm_spans = [
        s
        for s in spans
        if s.name == LLM_SPAN_NAME
        and s.context.trace_id == expected_trace_id
        and _is_descendant(s, server_span.context.span_id, by_id)
    ]
    assert llm_spans, (
        f"expected an llm.call span in the continued trace; got {[s.name for s in spans]}"
    )
