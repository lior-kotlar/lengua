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


def test_default_does_not_fold_diacritics_so_accents_stay_distinct() -> None:
    # fold=False (the default, for non-vowelized scripts): diacritics are meaning-bearing, so the
    # Spanish "está" (verb) is NOT treated as the known "esta" (demonstrative) — it survives as new.
    assert _dedup_unknown(["está", "agua"], known=["esta"], count=5) == ["está", "agua"]


def test_fold_drops_vowel_marked_variants_of_known_words() -> None:
    # fold=True (a vowelized language): a known word and a differently-vowel-marked surface of it
    # are the same word, so the marked suggestion is dropped rather than shown as new.
    # Hebrew: niqqud-marked "שָׁלוֹם" vs bare known "שלום".
    assert _dedup_unknown(["שָׁלוֹם", "תודה"], known=["שלום"], count=5, fold=True) == ["תודה"]
    # Arabic: harakat-marked "مَدْرَسَة" vs bare known "مدرسة".
    assert _dedup_unknown(["مَدْرَسَة", "كتاب"], known=["مدرسة"], count=5, fold=True) == ["كتاب"]


def test_fold_dedups_vowel_marked_duplicates_among_suggestions() -> None:
    # Two surfaces of the same vowelized word collapse to one (first spelling wins), like the
    # case-insensitive dedup but across vowel marks.
    assert _dedup_unknown(["שָׁלוֹם", "שלום", "תודה"], known=[], count=5, fold=True) == [
        "שָׁלוֹם",
        "תודה",
    ]
