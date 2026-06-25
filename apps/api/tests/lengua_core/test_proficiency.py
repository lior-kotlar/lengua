"""Task 1.1.3 — pure proficiency scoring.

``register_review`` returns the *new* score and never persists. Band math is pure.
``disable_socket`` proves no I/O.
"""

from __future__ import annotations

import pytest

from lengua_core import config, proficiency
from lengua_core.cards import PRODUCTION, RECOGNITION

pytestmark = pytest.mark.disable_socket


def test_clamp_score_bounds() -> None:
    assert proficiency.clamp_score(-5.0) == config.LEVEL_MIN
    assert proficiency.clamp_score(99.0) == config.LEVEL_MAX
    assert proficiency.clamp_score(2.5) == 2.5


def test_band_for_score_maps_and_clamps() -> None:
    assert proficiency.band_for_score(0.0) == "A1"
    assert proficiency.band_for_score(2.4) == "B1"
    assert proficiency.band_for_score(config.LEVEL_MAX) == "C2"  # upper index clamp
    assert proficiency.band_for_score(-1.0) == "A1"  # lower index clamp


def test_score_for_band_is_lower_bound_and_roundtrips() -> None:
    assert proficiency.score_for_band("A1") == 0.0
    assert proficiency.score_for_band("B1") == 2.0
    for band in config.CEFR_BANDS:
        assert proficiency.band_for_score(proficiency.score_for_band(band)) == band


def test_band_progress_fraction_and_full_at_cap() -> None:
    assert proficiency.band_progress(2.0) == 0.0
    assert proficiency.band_progress(2.5) == pytest.approx(0.5)
    assert proficiency.band_progress(config.LEVEL_MAX) == 1.0


def test_register_review_easy_recognition_nudges_up() -> None:
    new = proficiency.register_review(2.0, 4, RECOGNITION, gen_level=2.0)
    assert new == pytest.approx(2.0 + config.LEVEL_DELTAS[4])


def test_register_review_production_boosts_success_and_dampens_penalty() -> None:
    up = proficiency.register_review(2.0, 4, PRODUCTION, gen_level=2.0)
    assert up == pytest.approx(2.0 + config.LEVEL_DELTAS[4] * config.PROD_POS_WEIGHT)

    down = proficiency.register_review(2.0, 1, PRODUCTION, gen_level=2.0)
    assert down == pytest.approx(2.0 + config.LEVEL_DELTAS[1] * config.PROD_NEG_WEIGHT)


def test_register_review_again_recognition_nudges_down() -> None:
    new = proficiency.register_review(2.0, 1, RECOGNITION, gen_level=2.0)
    assert new == pytest.approx(2.0 + config.LEVEL_DELTAS[1])


def test_register_review_ignores_out_of_window_cards() -> None:
    # Card generated far below the current level must not move it.
    assert proficiency.register_review(4.0, 4, RECOGNITION, gen_level=0.0) == 4.0


def test_register_review_counts_legacy_cards_with_no_gen_level() -> None:
    new = proficiency.register_review(4.0, 4, RECOGNITION, gen_level=None)
    assert new == pytest.approx(4.0 + config.LEVEL_DELTAS[4])


def test_register_review_unknown_rating_is_a_no_op() -> None:
    assert proficiency.register_review(2.0, 0, RECOGNITION, gen_level=2.0) == 2.0


def test_register_review_clamps_to_bounds() -> None:
    # "Again" at the floor stays clamped, not negative.
    assert proficiency.register_review(0.0, 1, RECOGNITION, gen_level=0.0) == config.LEVEL_MIN
