"""Backend verify target: lint + format-check + types + tests.

Run from ``apps/api`` with::

    uv run python scripts/verify.py

Runs ruff lint, ruff format --check, mypy, and pytest (with coverage) in order,
stopping at the first failure. Exits non-zero if any step fails so it can gate CI
and the root ``make verify``.
"""

from __future__ import annotations

import subprocess
import sys

STEPS: list[tuple[str, list[str]]] = [
    ("ruff check", ["ruff", "check", "."]),
    ("ruff format --check", ["ruff", "format", "--check", "."]),
    ("mypy", ["mypy", "."]),
    ("pytest", ["pytest", "--cov", "--cov-branch"]),
]


def main() -> int:
    for label, cmd in STEPS:
        print(f"\n=== {label} ===", flush=True)
        result = subprocess.run(cmd)
        if result.returncode != 0:
            print(f"\nverify FAILED at: {label}", flush=True)
            return result.returncode
    print("\nverify OK — all checks passed", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
