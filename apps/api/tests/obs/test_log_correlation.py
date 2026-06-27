"""Task 5.3.2 verify: every log record emitted inside a request is correlated.

``test_in_request_log_carries_trace_span_and_user`` is the headline check: it drives a real
authenticated request (a real Supabase-shaped JWT, decoded by the real ``get_current_user`` — no
dependency override — so the per-request user-id contextvar is genuinely populated), logs a line
*inside* the request handler, and asserts the captured record's ``trace_id`` / ``span_id`` equal the
active server span's and ``user_id`` equals the token's user. The remaining tests cover the
:class:`~app.observability.TraceCorrelationFilter` branches directly (no active span / no user, and
that an explicitly-provided value is preserved).
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Iterator
from typing import Annotated

import pytest
from fastapi import Depends
from fastapi.testclient import TestClient
from opentelemetry import trace
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from app.deps import current_user
from app.main import create_app
from app.observability import TraceCorrelationFilter
from app.request_context import get_current_user_id, set_current_user_id
from tests.auth_helpers import auth_header, install_test_auth

#: Logger an in-request handler logs to (no real product code logs here, so the test owns it).
_IN_REQUEST_LOGGER = "lengua.test.in_request"


@pytest.fixture(autouse=True)
def _isolate_user_context() -> Iterator[None]:
    """Keep the per-request user-id contextvar from leaking between tests in this module.

    The direct-filter tests set it on the test's own context (no request task to isolate them), so
    reset it on entry and exit. The in-request test sets it inside the request's task, which has its
    own copied context, so this fixture never interferes with it.
    """
    set_current_user_id(None)
    try:
        yield
    finally:
        set_current_user_id(None)


@pytest.fixture
def captured_in_request_logs() -> Iterator[list[logging.LogRecord]]:
    """Capture records logged to the in-request logger, with the correlation filter applied."""
    records: list[logging.LogRecord] = []

    class _Capture(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            records.append(record)

    handler = _Capture()
    handler.addFilter(TraceCorrelationFilter())
    logger = logging.getLogger(_IN_REQUEST_LOGGER)
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    try:
        yield records
    finally:
        logger.removeHandler(handler)


def test_in_request_log_carries_trace_span_and_user(
    captured_in_request_logs: list[logging.LogRecord],
    span_exporter: InMemorySpanExporter,
) -> None:
    """A log emitted inside a request carries the active span's ids + the authenticated user id."""
    app = create_app()
    install_test_auth(app)  # verify the minted token; the real get_current_user runs (no override)
    in_request_logger = logging.getLogger(_IN_REQUEST_LOGGER)

    @app.get("/__probe__/log")
    async def _probe(user_id: Annotated[uuid.UUID, Depends(current_user)]) -> dict[str, str]:
        in_request_logger.info("inside the request")
        return {"user_id": str(user_id)}

    user_id = uuid.uuid4()
    with TestClient(app) as client:
        response = client.get("/__probe__/log", headers=auth_header(user_id))
    assert response.status_code == 200

    assert len(captured_in_request_logs) == 1
    record = captured_in_request_logs[0]

    server_spans = [
        s for s in span_exporter.get_finished_spans() if s.kind == trace.SpanKind.SERVER
    ]
    assert len(server_spans) == 1
    span_context = server_spans[0].context

    assert record.trace_id == format(span_context.trace_id, "032x")  # type: ignore[attr-defined]
    assert record.span_id == format(span_context.span_id, "016x")  # type: ignore[attr-defined]
    assert record.user_id == str(user_id)  # type: ignore[attr-defined]


def _stamp(record: logging.LogRecord) -> logging.LogRecord:
    """Run the correlation filter over ``record`` and return it (filter never drops a record)."""
    assert TraceCorrelationFilter().filter(record) is True
    return record


def _make_record() -> logging.LogRecord:
    return logging.LogRecord(
        name="lengua.test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="x",
        args=None,
        exc_info=None,
    )


def test_filter_sets_none_outside_a_request() -> None:
    """With no active span and no user set, the correlation fields are stamped as ``None``."""
    assert trace.get_current_span().get_span_context().is_valid is False
    assert get_current_user_id() is None

    record = _stamp(_make_record())

    assert record.trace_id is None  # type: ignore[attr-defined]
    assert record.span_id is None  # type: ignore[attr-defined]
    assert record.user_id is None  # type: ignore[attr-defined]


def test_filter_stamps_user_id_from_contextvar() -> None:
    """The filter reads the per-request user id from the contextvar (the non-``None`` branch)."""
    user_id = uuid.uuid4()
    set_current_user_id(user_id)

    record = _stamp(_make_record())

    assert record.user_id == str(user_id)  # type: ignore[attr-defined]


def test_filter_preserves_explicit_values() -> None:
    """An id already on the record (e.g. the access line's own ``trace_id``) is not overwritten."""
    record = _make_record()
    record.__dict__["trace_id"] = "explicit-trace-id"

    _stamp(record)

    assert record.trace_id == "explicit-trace-id"  # type: ignore[attr-defined]
    # span_id / user_id were absent, so the filter still fills them (here: None — no active span).
    assert record.span_id is None  # type: ignore[attr-defined]
    assert record.user_id is None  # type: ignore[attr-defined]
