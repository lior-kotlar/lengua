"""Unit tests for the per-user review-batch limit resolution (task 4.8b).

Pure (no DB): proves a stored ``daily_new_limit`` / ``daily_total_limit`` string is parsed to a
positive ``int`` and that a missing / blank / non-numeric / non-positive value falls back to the
``lengua_core.config`` default — the exact rule the ``GET /review/due`` wiring relies on so editing
the per-user limits actually bounds the due batch.
"""

from __future__ import annotations

import pytest

from app.services.review import (
    DAILY_NEW_LIMIT_KEY,
    DAILY_TOTAL_LIMIT_KEY,
    resolve_review_limit,
    resolve_review_limits,
)
from lengua_core import config


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("5", 5), ("  7 ", 7), ("1", 1), ("100", 100)],
)
def test_resolve_review_limit_parses_a_positive_int(raw: str, expected: int) -> None:
    # A non-default ``default`` proves the parsed value (not the fallback) is what's returned.
    assert resolve_review_limit(raw, default=42) == expected


@pytest.mark.parametrize(
    "raw",
    [None, "", "   ", "abc", "1.5", "12x", "-3", "0", "  -0 "],
)
def test_resolve_review_limit_falls_back_for_missing_blank_or_invalid(raw: str | None) -> None:
    # None / blank / non-numeric / non-positive all yield the config-style default, never a raise.
    assert resolve_review_limit(raw, default=42) == 42


def test_resolve_review_limits_reads_both_keys() -> None:
    new_limit, total_limit = resolve_review_limits(
        {DAILY_NEW_LIMIT_KEY: "3", DAILY_TOTAL_LIMIT_KEY: "8"}
    )
    assert (new_limit, total_limit) == (3, 8)


def test_resolve_review_limits_defaults_to_config_when_absent() -> None:
    assert resolve_review_limits({}) == (config.DAILY_NEW_LIMIT, config.DAILY_TOTAL_LIMIT)


def test_resolve_review_limits_defaults_each_key_independently() -> None:
    # A valid new limit + a blank total → parsed new, default total (each key resolved on its own).
    new_limit, total_limit = resolve_review_limits(
        {DAILY_NEW_LIMIT_KEY: "4", DAILY_TOTAL_LIMIT_KEY: "  "}
    )
    assert new_limit == 4
    assert total_limit == config.DAILY_TOTAL_LIMIT
