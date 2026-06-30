"""Unit tests for the pure typed-key bounds validation (finding S9).

:func:`app.services.settings.validate_numeric_bound` is the write-side guard that keeps a stored
``daily_*_limit`` / ``discover_count`` inside what the review batch and a Discover request accept.
It is pure (no I/O), so it is tested directly here; the cross-field rule and the delete-on-``None``
path are covered by the service / API integration tests.
"""

from __future__ import annotations

import pytest

from app.schemas.discover import DiscoverRequest
from app.services.errors import ValidationError
from app.services.settings import (
    DISCOVER_COUNT_KEY,
    NUMERIC_SETTING_BOUNDS,
    validate_numeric_bound,
)


def test_unknown_key_is_unconstrained() -> None:
    # A key with no typed bound stays free-form: any string is accepted (the store is generic).
    validate_numeric_bound("some_freeform_pref", "anything at all")


@pytest.mark.parametrize("key", list(NUMERIC_SETTING_BOUNDS))
def test_inclusive_endpoints_accepted(key: str) -> None:
    low, high = NUMERIC_SETTING_BOUNDS[key]
    validate_numeric_bound(key, str(low))
    validate_numeric_bound(key, str(high))
    # Surrounding whitespace is tolerated (consumers strip the value on read).
    validate_numeric_bound(key, f"  {high}  ")


@pytest.mark.parametrize("key", list(NUMERIC_SETTING_BOUNDS))
def test_out_of_range_rejected(key: str) -> None:
    low, high = NUMERIC_SETTING_BOUNDS[key]
    with pytest.raises(ValidationError):
        validate_numeric_bound(key, str(low - 1))
    with pytest.raises(ValidationError):
        validate_numeric_bound(key, str(high + 1))


@pytest.mark.parametrize("bad", ["abc", "1.5", "", "  ", "10x", "0x10", "five"])
def test_non_integer_rejected(bad: str) -> None:
    with pytest.raises(ValidationError):
        validate_numeric_bound("daily_new_limit", bad)


def test_discover_count_bound_tracks_request_schema() -> None:
    # The discover_count bound is single-sourced from DiscoverRequest.count, so a stored preference
    # can never exceed what POST /discover accepts — and the two can never silently drift apart.
    count_schema = DiscoverRequest.model_json_schema()["properties"]["count"]
    assert NUMERIC_SETTING_BOUNDS[DISCOVER_COUNT_KEY] == (
        int(count_schema["minimum"]),
        int(count_schema["maximum"]),
    )
