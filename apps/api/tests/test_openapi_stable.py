"""Contract test (task 1.6.1): the committed ``apps/api/openapi.json`` must match the live schema.

The OpenAPI document is the contract the typed TS client in ``packages/api-types`` is generated
from. If a router/schema change makes ``app.openapi()`` drift from the committed file, this fails
the PR; the fix is to regenerate::

    python apps/api/scripts/dump_openapi.py        # rewrites openapi.json
    pnpm --filter api-types generate               # re-derives the TS types

Both this test and the dump script build the schema with the test-only ``/__test__/*`` routes
excluded, so the contract is the real public API regardless of ``LLM_PROVIDER``.
"""

from __future__ import annotations

import copy

from scripts.dump_openapi import OPENAPI_PATH, build_schema, serialize


def test_committed_openapi_matches_app() -> None:
    """The checked-in openapi.json is byte-identical to the app's current schema."""
    assert OPENAPI_PATH.exists(), (
        f"{OPENAPI_PATH} is missing — run `python apps/api/scripts/dump_openapi.py`."
    )
    committed = OPENAPI_PATH.read_text(encoding="utf-8")
    current = serialize(build_schema())
    assert committed == current, (
        "apps/api/openapi.json is stale vs app.openapi(). Regenerate it with "
        "`python apps/api/scripts/dump_openapi.py` and re-run `pnpm --filter api-types generate`."
    )


def test_public_schema_excludes_test_only_routes() -> None:
    """The contract never leaks the ``/__test__/*`` routes (they are E2E-only)."""
    schema = build_schema()
    assert "/health" in schema["paths"]
    assert not any(p.startswith("/__test__") for p in schema["paths"]), schema["paths"].keys()


def test_drift_is_detected() -> None:
    """Guard the guard: a changed schema must NOT match the committed contract."""
    tampered = copy.deepcopy(build_schema())
    tampered["paths"].pop("/health")  # simulate an endpoint being removed
    assert serialize(tampered) != OPENAPI_PATH.read_text(encoding="utf-8")
