"""THROWAWAY proof module (0.5.3) — reverted right after CI proves coverage<80% fails.

Deliberately uncovered branchy logic under `app/` (a coverage source) so the backend
coverage drops below the 80% gate. No test imports or exercises this.
"""

from __future__ import annotations


def proof_branch(n: int) -> str:
    """Several uncovered branches to push line+branch coverage under 80%."""
    if n > 100:
        return "huge"
    if n > 10:
        return "big"
    if n > 0:
        return "small"
    if n == 0:
        return "zero"
    return "negative"


def proof_more(items: list[int]) -> int:
    total = 0
    for it in items:
        if it % 2 == 0:
            total += it
        else:
            total -= it
    return total
