"""Per-language proficiency level: a continuous CEFR score that shapes generation
and self-updates from review answers.

The score runs 0..6 on the CEFR scale (band = ``CEFR_BANDS[floor(score)]``). It rises
on "Easy", drifts down on "Again"/"Hard", and treats production cards (English->target,
the harder direction) asymmetrically — more credit for success, less penalty for a
struggle. Only reviews of roughly current-level material count, so a backlog of old or
below-level cards can't inflate the level.

State is keyed by ``(user_id, language_id)`` with a single default user for now.
"""
from . import config
from .db import connect


def _clamp(score: float) -> float:
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


def get_score(language_id: int, user_id: int = config.DEFAULT_USER_ID) -> float:
    """The learner's continuous score for a language (0.0 / A1 if not set yet)."""
    with connect() as conn:
        row = conn.execute(
            "SELECT score FROM proficiency WHERE user_id = ? AND language_id = ?",
            (user_id, language_id),
        ).fetchone()
    return float(row["score"]) if row else config.LEVEL_MIN


def get_band(language_id: int, user_id: int = config.DEFAULT_USER_ID) -> str:
    return band_for_score(get_score(language_id, user_id))


def set_score(
    language_id: int, score: float, user_id: int = config.DEFAULT_USER_ID
) -> float:
    """Upsert the clamped score and return the stored value."""
    score = _clamp(score)
    with connect() as conn:
        conn.execute(
            "INSERT INTO proficiency (user_id, language_id, score) VALUES (?, ?, ?) "
            "ON CONFLICT(user_id, language_id) DO UPDATE SET "
            "score = excluded.score, updated_at = datetime('now')",
            (user_id, language_id, score),
        )
    return score


def set_band(
    language_id: int, band: str, user_id: int = config.DEFAULT_USER_ID
) -> float:
    """Manually place the learner at a CEFR band (sets the score to its lower bound)."""
    return set_score(language_id, score_for_band(band), user_id)


def register_review(
    language_id: int,
    rating: int,
    direction: str | None,
    gen_level: float | None,
    user_id: int = config.DEFAULT_USER_ID,
) -> None:
    """Nudge the language score after one review.

    `gen_level` is the score the reviewed card was generated at (None for legacy/imported
    cards, which always count). `direction` weights the nudge: production cards get more
    credit for success and less penalty for a struggle.
    """
    score = get_score(language_id, user_id)
    if gen_level is not None and abs(gen_level - score) > config.LEVEL_WINDOW:
        return  # not current-level material — ignore so old/easy cards don't inflate

    delta = config.LEVEL_DELTAS.get(int(rating), 0.0)
    from .flashcards import PRODUCTION  # deferred: flashcards -> scheduler -> proficiency

    if direction == PRODUCTION:
        delta *= config.PROD_POS_WEIGHT if delta > 0 else config.PROD_NEG_WEIGHT
    if delta:
        set_score(language_id, score + delta, user_id)
