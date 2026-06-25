"""Dump the live FastAPI OpenAPI schema to the checked-in ``apps/api/openapi.json``.

The committed ``openapi.json`` is the **contract** the typed TypeScript client in
``packages/api-types`` is generated from (task 1.6). Run this whenever the HTTP surface
changes::

    python apps/api/scripts/dump_openapi.py

CI's ``tests/test_openapi_stable.py`` fails if the committed file drifts from the app's current
schema, and ``pnpm --filter api-types generate`` re-derives the TS types from it.

The schema is built with the **test-only** routes excluded (``include_test_routes=False``) so the
contract reflects the real public API and never depends on the runtime ``LLM_PROVIDER`` (the
backend test job runs with ``LLM_PROVIDER=fake``, which would otherwise mount ``/__test__/*``).
Serialization is deterministic — sorted keys + a trailing newline — so the file is stable across
machines and the drift check is a plain byte comparison.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

# Make ``app`` importable when this is run directly (``python apps/api/scripts/dump_openapi.py``),
# where only ``scripts/`` — not its parent ``apps/api`` — is on ``sys.path``. Under pytest the
# parent is already on the path, so this is a harmless no-op there.
_API_ROOT = Path(__file__).resolve().parent.parent
if str(_API_ROOT) not in sys.path:
    sys.path.insert(0, str(_API_ROOT))

if TYPE_CHECKING:
    from fastapi import FastAPI

# ``apps/api/openapi.json`` — scripts/ -> parent is apps/api.
OPENAPI_PATH = _API_ROOT / "openapi.json"


def build_schema() -> dict[str, Any]:
    """Return the canonical public OpenAPI schema (test-only routes excluded)."""
    # Imported here (not at module top) so the sys.path bootstrap above runs first.
    from app.main import create_app

    app: FastAPI = create_app(include_test_routes=False)
    return app.openapi()


def serialize(schema: dict[str, Any]) -> str:
    """Serialize a schema deterministically (stable key order + trailing newline)."""
    return json.dumps(schema, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def write(path: Path = OPENAPI_PATH) -> Path:
    """Write the serialized canonical schema to ``path`` (forcing LF) and return it."""
    # newline="\n" keeps the file LF even when this runs on Windows, so the committed contract
    # is byte-identical everywhere and ``git diff`` / the drift test stay clean cross-platform.
    path.write_text(serialize(build_schema()), encoding="utf-8", newline="\n")
    return path


def main() -> None:
    """CLI entrypoint: (re)write ``openapi.json`` and report where."""
    path = write()
    print(f"wrote {path}")


if __name__ == "__main__":
    main()
