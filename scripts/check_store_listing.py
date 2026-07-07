#!/usr/bin/env python3
"""Store-listing character-limit check (Phase 8, task 8.7.1).

Asserts the character-limited fields in ``docs/store-listing.md`` fit within the **shorter** of the
Apple App Store and Google Play limits, so one set of copy works for both stores (the same copy is
reused per store). Stdlib-only, no network — a fast, deterministic CI gate.

Usage: python3 scripts/check_store_listing.py
Exit 0 = all fields within limits; 1 = at least one overflows (printed).
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOC = ROOT / "docs" / "store-listing.md"

# Each capped field → the SHORTER of the two stores' limits.
#   name/title: Apple app name 30, Play title 30 → 30
#   subtitle:   Apple subtitle 30 (Play has none) → 30
#   short_description: Play short description 80 (Apple has none) → 80
#   keywords:   Apple keywords 100 chars incl. commas (Play has none) → 100
LIMITS = {"name": 30, "subtitle": 30, "short_description": 80, "keywords": 100}
FULL_DESCRIPTION_LIMIT = 4000  # both stores cap the full description at 4000


def _block(text: str, name: str) -> str:
    match = re.search(rf"<!-- {name}:start -->(.*?)<!-- {name}:end -->", text, re.DOTALL)
    if match is None:
        raise SystemExit(f"store-listing check: missing <!-- {name}:start/end --> block in {DOC.name}")
    return match.group(1)


def main() -> int:
    text = DOC.read_text(encoding="utf-8")

    fields: dict[str, str] = {}
    for line in _block(text, "store-fields").splitlines():
        match = re.match(r"\s*-\s*([a-z_]+):\s*(.*\S)\s*$", line)
        if match:
            fields[match.group(1)] = match.group(2)

    errors: list[str] = []
    for key, limit in LIMITS.items():
        if key not in fields:
            errors.append(f"missing field '{key}'")
            continue
        length = len(fields[key])
        if length > limit:
            errors.append(f"{key} is {length} chars (limit {limit}): {fields[key]!r}")

    full = _block(text, "full-description").strip()
    if len(full) > FULL_DESCRIPTION_LIMIT:
        errors.append(f"full description is {len(full)} chars (limit {FULL_DESCRIPTION_LIMIT})")

    if errors:
        print("::error::store-listing field(s) exceed the store character limits:", file=sys.stderr)
        for entry in errors:
            print(f"  {entry}", file=sys.stderr)
        return 1
    print(f"store-listing check OK: {len(LIMITS)} capped fields + full description within limits.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
