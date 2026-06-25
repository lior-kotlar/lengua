"""Task 1.5.1 verify: ``GET /health`` returns 200 ``{"status": "ok"}``.

A plain unit test (no DB): builds the app via :func:`app.main.create_app` and hits ``/health``
with the in-process ``TestClient``.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import create_app


def test_health_returns_ok() -> None:
    with TestClient(create_app()) as client:
        response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
