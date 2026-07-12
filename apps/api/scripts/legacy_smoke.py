"""Guard the "keep the legacy Streamlit app runnable" contract in CI (a standing CLAUDE.md rule).

The legacy Streamlit app (:mod:`legacy_streamlit`) is kept runnable throughout the
productionization rebuild, but until now that promise had **zero automated coverage** — while its
highest-churn dependency, :mod:`lengua_core.prompts`, gets rewritten (e.g. GitHub #80/#150). A pure
refactor of ``lengua_core`` that renamed a symbol the legacy pages import, or broke the prompt
builders' interpolation, would silently break the app with nothing failing in CI. This script is
that missing guard: a fast (<1 min), dependency-light smoke run as a CI step.

**Why not just run the pages.** The four page bodies
(``pages/{1_Generate,2_Review,3_Discover,4_Settings}.py``) are written for a real Streamlit
runtime. Run bare (no ``ScriptRunContext``), ``st.stop()`` is a no-op, so a page body runs *past*
its "no active language / empty deck" guards and then crashes on empty state (``2_Review`` indexes
into an empty due-batch). Executing the page bodies is therefore fundamentally unreliable and would
make this guard flaky for reasons unrelated to the contract it protects.

**What it does instead** — four checks that fail loudly (non-zero exit) the moment a ``lengua_core``
change would break the legacy app, without ever running a fragile page body:

1. **Import the legacy support modules** directly (``app``, ``ui``, ``db``, ``store``, ``settings``,
   ``languages``). These import cleanly; ``app`` runs ``render_sidebar`` at import, so bare-mode
   ``ScriptRunContext`` warnings on stderr are expected — but any *exception* is a failure.
2. **Resolve each page's imports** by parsing its source with :mod:`ast`, extracting only the
   top-level ``import`` / ``from ... import ...`` statements, and executing exactly those. This
   binds every symbol the page depends on (e.g. ``from lengua_core.gemini import generate_cards,
   suggest_new_words``) — precisely what a ``lengua_core`` refactor would break — without running
   the page body.
3. **Byte-compile the four pages** (:mod:`compileall`) as a syntax guard.
4. **Call the prompt builders the legacy path uses** (``prompts.system_instruction`` /
   ``prompts.suggestion_instruction`` under the no-DB-override default the legacy app runs with)
   and assert non-empty output with the ``{language}`` / ``{level}`` placeholders interpolated.

Run locally (streamlit is deliberately NOT an ``apps/api`` dependency — the legacy app pins its
own deps in the repo-root ``requirements.txt`` for humans)::

    uv run --with streamlit python scripts/legacy_smoke.py

Exits 0 when the contract holds, non-zero (with a diagnostic) on the first failure.
"""

from __future__ import annotations

import ast
import compileall
import importlib
import os
import sys
import tempfile
from pathlib import Path

# ``apps/api`` — scripts/ -> parent. Put it on sys.path so ``legacy_streamlit`` / ``lengua_core``
# import when this is run directly (``python scripts/legacy_smoke.py``), where only ``scripts/`` is
# on the path.
_API_ROOT = Path(__file__).resolve().parent.parent
if str(_API_ROOT) not in sys.path:
    sys.path.insert(0, str(_API_ROOT))

_PAGES_DIR = _API_ROOT / "legacy_streamlit" / "pages"
_PAGES = ("1_Generate.py", "2_Review.py", "3_Discover.py", "4_Settings.py")

# The legacy support modules the pages build on. Importing them exercises every module-level
# import (their ``lengua_core`` dependencies) and, for ``app``, the render_sidebar-at-import path.
_SUPPORT_MODULES = (
    "legacy_streamlit.app",
    "legacy_streamlit.ui",
    "legacy_streamlit.db",
    "legacy_streamlit.store",
    "legacy_streamlit.settings",
    "legacy_streamlit.languages",
)


def check_support_module_imports() -> None:
    """Import each legacy support module; any exception fails the contract.

    ``legacy_streamlit.app`` runs ``render_sidebar()`` at import, which (in a real runtime) touches
    the SQLite DB via ``init_db``. ``LENGUA_DB_PATH`` is pointed at a throwaway temp file by
    :func:`main` so this never writes into the repo tree.
    """
    print("[1/4] importing legacy support modules")
    for name in _SUPPORT_MODULES:
        importlib.import_module(name)
        print(f"      ok  {name}")


def _import_only_source(page: Path) -> str:
    """Return source containing only ``page``'s top-level import statements, in order.

    Parses ``page`` with :mod:`ast` and re-emits each top-level ``import`` / ``from ... import ...``
    node via :func:`ast.unparse`. The page body (which needs a live Streamlit runtime) is dropped.
    """
    tree = ast.parse(page.read_text(encoding="utf-8"), filename=str(page))
    imports = [node for node in tree.body if isinstance(node, ast.Import | ast.ImportFrom)]
    return "\n".join(ast.unparse(node) for node in imports)


def check_page_imports() -> None:
    """Execute each page's top-level imports so every symbol it depends on must still resolve.

    This is the core of the guard: ``from lengua_core.gemini import generate_cards`` (etc.) fails
    with ``ImportError`` the instant a ``lengua_core`` refactor renames or drops a symbol the legacy
    pages rely on — without running the fragile page body.
    """
    print("[2/4] resolving each page's imports")
    for filename in _PAGES:
        page = _PAGES_DIR / filename
        source = _import_only_source(page)
        code = compile(source, filename=f"<{filename}:imports>", mode="exec")
        # A fresh namespace per page so one page's imports can't mask a break in another's.
        exec(code, {"__name__": f"legacy_smoke.{filename}"})  # noqa: S102
        print(f"      ok  {filename}")


def check_pages_compile() -> None:
    """Byte-compile the four page files (syntax guard)."""
    print("[3/4] byte-compiling the four pages")
    for filename in _PAGES:
        page = _PAGES_DIR / filename
        if not compileall.compile_file(str(page), quiet=1):
            raise SystemExit(f"legacy smoke: syntax error compiling {page}")
        print(f"      ok  {filename}")


def check_prompt_builders() -> None:
    """Call the prompt builders the legacy generation path uses and assert correct output.

    The legacy app installs no DB override source, so the builders run against the code defaults
    (:data:`lengua_core.prompts.CODE_DEFAULTS`). This asserts the assembled instruction is non-empty
    and that the ``{language}`` / ``{level}`` placeholders interpolated — the exact failure mode a
    prompts.py rewrite (GitHub #80/#150) could introduce for the legacy path.
    """
    print("[4/4] exercising the lengua_core prompt builders")
    from lengua_core import prompts

    system = prompts.system_instruction("Spanish", vowelized=True, level="A2")
    if not system.strip():
        raise SystemExit("legacy smoke: system_instruction() returned empty output")
    for needle in ("Spanish", "A2"):
        if needle not in system:
            raise SystemExit(f"legacy smoke: system_instruction() did not interpolate {needle!r}")
    if "{language}" in system or "{level}" in system:
        raise SystemExit("legacy smoke: system_instruction() left an un-interpolated placeholder")

    suggestion = prompts.suggestion_instruction(
        "Spanish", "A2", known_words=["casa", "perro"], count=5, topic="food"
    )
    if not suggestion.strip():
        raise SystemExit("legacy smoke: suggestion_instruction() returned empty output")
    for needle in ("Spanish", "5", "food", "casa"):
        if needle not in suggestion:
            raise SystemExit(
                f"legacy smoke: suggestion_instruction() did not interpolate {needle!r}"
            )
    print("      ok  system_instruction + suggestion_instruction")


def main() -> int:
    # Importing ``legacy_streamlit.app`` runs ``init_db`` against ``config.DB_PATH``; point it at a
    # throwaway temp file so the smoke never writes into (and dirties) the repo tree.
    with tempfile.TemporaryDirectory(prefix="legacy-smoke-") as tmp:
        os.environ["LENGUA_DB_PATH"] = str(Path(tmp) / "legacy_smoke.db")
        check_support_module_imports()
        check_page_imports()
        check_pages_compile()
        check_prompt_builders()
    print("\nlegacy smoke OK - the legacy Streamlit app is still runnable against lengua_core.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
