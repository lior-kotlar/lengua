#!/usr/bin/env python3
"""Deterministic markdown link check for the published docs (Phase 8, task 8.1.1).

Validates that every *relative* markdown link in the documentation set resolves to a file that
actually exists in the repo — so a published page (privacy policy, support, store listing) never
ships a dead intra-repo link. External links (http/https/mailto/tel) and pure in-page anchors
(`#section`) are intentionally skipped: hitting the network would be flaky and is out of scope for a
CI gate. This is stdlib-only (no deps, no network) so it runs as a fast, hermetic CI step.

Usage: python3 scripts/check_doc_links.py
Exit code 0 = all relative links resolve; 1 = at least one dead link (printed).
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

# Repo root = the parent of this script's directory (scripts/).
ROOT = Path(__file__).resolve().parent.parent

# The documentation set we hold to "no dead links". Kept to the published-facing docs plus the two
# root records; planning/** is intentionally excluded (forward-only churn, not published).
DOC_GLOBS = (
    "docs/**/*.md",
    "README.md",
    "CHANGELOG.md",
)

# Inline markdown links: [text](target). Capturing group 1 is the target (may carry a #anchor and/or
# a "title"). Image links ![alt](src) are matched too (the leading ! is fine — src is still a path).
_LINK_RE = re.compile(r"\[[^\]]*\]\(([^)]+)\)")

# Schemes/prefixes we do not resolve on disk.
_SKIP_PREFIXES = ("http://", "https://", "mailto:", "tel:", "#")


def _iter_doc_files() -> list[Path]:
    seen: dict[Path, None] = {}
    for glob in DOC_GLOBS:
        for path in sorted(ROOT.glob(glob)):
            if path.is_file():
                seen.setdefault(path.resolve(), None)
    return list(seen)


def _target_path(link: str) -> str | None:
    """Return the on-disk relative path a link points at, or None if it should be skipped."""
    target = link.strip().split()[0]  # drop any `"title"` after the URL
    if not target or target.startswith(_SKIP_PREFIXES):
        return None
    # Strip a trailing in-page anchor (e.g. runbook.md#deploy -> runbook.md).
    return target.split("#", 1)[0] or None


def main() -> int:
    dead: list[str] = []
    checked = 0
    files = _iter_doc_files()
    for md in files:
        text = md.read_text(encoding="utf-8")
        for match in _LINK_RE.finditer(text):
            rel = _target_path(match.group(1))
            if rel is None:
                continue
            checked += 1
            resolved = (md.parent / rel).resolve()
            if not resolved.exists():
                dead.append(f"{md.relative_to(ROOT).as_posix()} -> {match.group(1)}")

    print(f"doc-link-check: scanned {len(files)} files, {checked} relative links.")
    if dead:
        print(f"::error::{len(dead)} dead relative link(s) found in docs:", file=sys.stderr)
        for entry in dead:
            print(f"  dead link: {entry}", file=sys.stderr)
        return 1
    print("doc-link-check OK: all relative links resolve.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
