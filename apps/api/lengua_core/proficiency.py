"""Per-language proficiency level: a continuous CEFR score that shapes generation and
self-updates from review answers.

The score runs 0..6 on the CEFR scale (band = ``CEFR_BANDS[floor(score)]``). It rises on
"Easy", drifts down on "Again"/"Hard", and treats production cards (English->target, the
harder direction) asymmetrically — more credit for success, less penalty for a struggle. Only
reviews of roughly current-level material count, so a backlog of old or below-level cards can't
inflate the level.

This module is **pure**: it computes scores and bands but never persists anything.
:func:`register_review` takes the current score and returns the new one; storing it (keyed by
``(user_id, language_id)``) is the caller's job — the legacy SQLite store or the API's
proficiency repository.
"""

from __future__ import annotations

from . import config
from .cards import PRODUCTION

__all__ = [
    "clamp_score",
    "band_for_score",
    "score_for_band",
    "band_progress",
    "register_review",
]


def clamp_score(score: float) -> float:
    """Clamp a score into the valid CEFR range ``[LEVEL_MIN, LEVEL_MAX]``."""
    return max(config.LEVEL_MIN, min(config.LEVEL_MAX, score))


def band_for_score(score: float) -> str:
    """CEFR band label for a continuous score (e.g. 2.4 -> 'B1')."""
    idx = int(score)
    idx = max(0, min(idx, len(config.CEFR_BANDS) - 1))
    return config.CEFR_BANDS[idx]


def score_for_band(band: str) -> float:
    """Lower-bound score of a CEFR band (e.g. 'B1' -> 2.0). Used for manual overrides."""
    return float(config.CEFR_BANDS.index(band))


def band_progress(score: float) -> float:
    """Fractional progress through the current band, 0..1 (for a progress bar).

    Capped at the top of C2 so a maxed-out learner shows a full bar.
    """
    if score >= config.LEVEL_MAX:
        return 1.0
    return score - int(score)


def register_review(
    current_score: float,
    rating: int,
    direction: str | None,
    gen_level: float | None,
) -> float:
    """Return the new language score after one review (pure — no persistence).

    ``current_score`` is the learner's score before this review. ``gen_level`` is the score the
    reviewed card was generated at (``None`` for legacy/imported cards, which always count); a
    card more than :data:`config.LEVEL_WINDOW` bands from the current score is ignored so old or
    below-level cards can't move the level. ``direction`` weights the nudge: production cards get
    more credit for success and less penalty for a struggle. When nothing should move, the
    unchanged ``current_score`` is returned.
    """
    if gen_level is not None and abs(gen_level - current_score) > config.LEVEL_WINDOW:
        return current_score  # not current-level material — ignore

    delta = config.LEVEL_DELTAS.get(int(rating), 0.0)
    if direction == PRODUCTION:
        delta *= config.PROD_POS_WEIGHT if delta > 0 else config.PROD_NEG_WEIGHT
    if not delta:
        return current_score
    return clamp_score(current_score + delta)
