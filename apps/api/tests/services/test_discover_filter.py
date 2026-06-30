"""Unit tests for the discover suggestion filter (finding S15).

:func:`app.services.discover._dedup_unknown` is the service-layer guard behind the generation
prompt: the prompt *asks* the model to exclude vocabulary the learner already has, and this
*enforces* it — case-insensitively, dropping duplicates and blanks, then trimming to ``count``.
Pure (no DB / no provider), so these run in the plain unit suite offline.
"""

from __future__ import annotations

from app.services.discover import _dedup_unknown


def test_drops_known_case_insensitively() -> None:
    # "Casa" is the same word as the known "casa"; matching ignores case on both sides.
    assert _dedup_unknown(["Casa", "agua", "pan"], known=["casa"], count=5) == ["agua", "pan"]


def test_dedups_keeping_first_spelling() -> None:
    # "Agua"/"agua" collapse to a single entry; the first spelling encountered wins.
    assert _dedup_unknown(["Agua", "agua", "AGUA", "pan"], known=[], count=5) == ["Agua", "pan"]


def test_skips_blank_and_trims_whitespace() -> None:
    assert _dedup_unknown(["  pan  ", "", "   ", "leche"], known=[], count=5) == ["pan", "leche"]


def test_trims_to_count_after_filtering() -> None:
    # The trim happens only after known/dupe words are removed, so dropped words don't shrink the
    # result below ``count`` when enough genuinely-new candidates remain.
    raw = ["casa", "agua", "pan", "leche", "sol", "pez"]
    assert _dedup_unknown(raw, known=["casa"], count=3) == ["agua", "pan", "leche"]


def test_non_positive_count_returns_empty() -> None:
    assert _dedup_unknown(["agua", "pan"], known=[], count=0) == []
    assert _dedup_unknown(["agua", "pan"], known=[], count=-1) == []


def test_all_known_returns_empty() -> None:
    assert _dedup_unknown(["Casa", "AGUA"], known=["casa", "agua"], count=5) == []
