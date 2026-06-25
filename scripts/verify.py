"""Root one-command verify: fan out to the api and web verify targets.

This is the cross-platform engine behind ``make verify`` (see the root ``Makefile``).
Run it directly when ``make`` is unavailable (e.g. on Windows)::

    python scripts/verify.py          # or: uv run --project apps/api python scripts/verify.py

It runs, in order:

1. the **api** verify target  — ``uv run python scripts/verify.py`` in ``apps/api``
   (ruff lint, ruff format --check, mypy, pytest with branch coverage), and
2. the **web** verify target  — ``pnpm verify`` in ``apps/web``
   (eslint, prettier --check, tsc --noEmit, vitest with coverage, vite build).

It stops at the first failing app and exits non-zero so it can gate local work and CI.
``pnpm`` is invoked via ``corepack pnpm`` when ``pnpm`` is not on ``PATH`` (corepack
honors the ``packageManager`` pin in ``apps/web/package.json`` and ships with Node).
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
API_DIR = ROOT / "apps" / "api"
WEB_DIR = ROOT / "apps" / "web"


def _exe(name: str) -> str:
    """Resolve ``name`` to a full path so Windows can launch ``.cmd``/``.exe`` shims.

    On Windows, ``subprocess`` with ``shell=False`` cannot run a bare ``corepack`` or
    ``uv`` (they are ``.cmd``/``.exe`` files resolved by the shell, not ``CreateProcess``);
    ``shutil.which`` returns the concrete path with the right extension. Falls back to the
    bare name (so the failure message is obvious) when the tool isn't found.
    """
    return shutil.which(name) or name


def _pnpm_cmd() -> list[str]:
    """Return the pnpm invocation, preferring a PATH ``pnpm`` then ``corepack pnpm``."""
    if shutil.which("pnpm"):
        return [_exe("pnpm")]
    if shutil.which("corepack"):
        return [_exe("corepack"), "pnpm"]
    # Fall through to a bare "pnpm" so the failure message is obvious.
    return ["pnpm"]


# (label, working dir, command) — run in order, stop at first failure.
STEPS: list[tuple[str, Path, list[str]]] = [
    ("api verify", API_DIR, [_exe("uv"), "run", "python", "scripts/verify.py"]),
    ("web verify", WEB_DIR, [*_pnpm_cmd(), "verify"]),
]


def main() -> int:
    for label, cwd, cmd in STEPS:
        print(f"\n========== {label} ({' '.join(cmd)}) ==========", flush=True)
        result = subprocess.run(cmd, cwd=cwd, shell=False)
        if result.returncode != 0:
            print(f"\nverify FAILED at: {label}", flush=True)
            return result.returncode
    print("\nverify OK — api + web all green", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
