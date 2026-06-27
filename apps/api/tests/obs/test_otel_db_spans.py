"""Task 5.1.3 verify: SQLAlchemy queries become child spans under the FastAPI server span.

``test_db_select_span_is_child_of_server_span`` (``@integration``) hits ``GET /languages`` with an
authed test user over the real Supabase-CLI Postgres and asserts the SQLAlchemy ``SELECT`` span
shares the server span's trace id and nests under it.

``test_get_engine_builds_instrumented_engine`` is the offline guard for the production wiring: the
OTel SQLAlchemy auto-instrumentation only attaches its per-statement ``EngineTracer`` to engines
built through the *wrapped* ``create_async_engine``. :func:`app.db.session.get_engine` resolves that
factory on the module **at call time** so the app engine emits statement spans; a regression back to
a module-level ``from … import create_async_engine`` would re-capture the unwrapped factory and
silently drop every DB span. This test fails loudly if that happens.
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

# Importing app.main runs create_app() -> configure_observability(), wrapping create_async_engine.
import app.main  # noqa: F401
from app.db.session import async_dsn
from app.deps import DEV_USER_ID, get_db
from app.main import create_app
from tests.auth_helpers import auth_header, install_test_auth
from tests.conftest import _skip_if_db_unreachable, database_url


@pytest.mark.asyncio
async def test_get_engine_builds_instrumented_engine(monkeypatch: pytest.MonkeyPatch) -> None:
    """get_engine builds the app engine via the OTel-wrapped create_async_engine (task 5.1.3).

    Exercises the production helper with a dummy DSN (engine creation is lazy — no connection) and
    asserts the engine carries SQLAlchemy statement instrumentation: the ``EngineTracer``'s
    ``before_cursor_execute`` listener is registered only when the engine was built through the
    *instrumented* factory. Guards the late binding in :func:`app.db.session.get_engine` against a
    regression to a module-level import of the unwrapped factory (which would drop all DB spans).
    """
    import app.db.session as db_session_mod
    from app.settings import Settings

    dummy = Settings(  # type: ignore[call-arg]
        _env_file=None, database_url="postgresql://u:p@127.0.0.1:5999/db"
    )
    monkeypatch.setattr(db_session_mod, "get_settings", lambda: dummy)
    monkeypatch.setattr(
        db_session_mod, "_engine", None
    )  # build a fresh engine, restored at teardown
    monkeypatch.setattr(db_session_mod, "_sessionmaker", None)

    engine = db_session_mod.get_engine()
    try:
        assert bool(engine.sync_engine.dispatch.before_cursor_execute)
    finally:
        await engine.dispose()


@pytest_asyncio.fixture
async def languages_client(clean_db: None) -> AsyncIterator[AsyncClient]:
    """ASGI client whose ``get_db`` is an *instrumented* engine's rolled-back session (dev user)."""
    from scripts.seed_dev_user import seed_dev_user

    _skip_if_db_unreachable()
    seed_dev_user()  # committed dev profile so the request resolves to a real user

    # Build via the module attribute so the OTel-wrapped create_async_engine attaches the
    # EngineTracer (the same path get_engine uses) -> SELECT/INSERT statement spans are emitted.
    engine = sa_asyncio.create_async_engine(async_dsn(database_url()))
    conn = await engine.connect()
    trans = await conn.begin()
    session = AsyncSession(
        bind=conn, expire_on_commit=False, join_transaction_mode="create_savepoint"
    )

    app = create_app()

    async def _override_get_db() -> AsyncIterator[AsyncSession]:
        yield session

    app.dependency_overrides[get_db] = _override_get_db
    install_test_auth(app)  # verify the real bearer token against the test secret

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
async def test_db_select_span_is_child_of_server_span(
    languages_client: AsyncClient, span_exporter: InMemorySpanExporter
) -> None:
    response = await languages_client.get("/languages", headers=auth_header(DEV_USER_ID))
    assert response.status_code == 200, response.text

    spans = span_exporter.get_finished_spans()
    server_spans = [
        s for s in spans if s.kind == trace.SpanKind.SERVER and "/languages" in (s.name or "")
    ]
    assert server_spans, f"expected a GET /languages server span; got {[s.name for s in spans]}"
    server_span = server_spans[0]

    # SQLAlchemy names a statement span after the operation (+ db name), e.g. "SELECT postgres".
    select_spans = [s for s in spans if (s.name or "").upper().startswith("SELECT")]
    assert select_spans, f"expected a SQLAlchemy SELECT span; got {[s.name for s in spans]}"

    by_id = {s.context.span_id: s for s in spans}
    nested = [
        s
        for s in select_spans
        if s.context.trace_id == server_span.context.trace_id
        and _is_descendant(s, server_span.context.span_id, by_id)
    ]
    assert nested, "expected a SQLAlchemy SELECT span nested under the GET /languages server span"
