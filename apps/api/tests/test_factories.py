"""Tests for the test-data builders (task 0.4.1).

Verifies each ``make_*`` builds the entity with its required (NOT NULL / no-default) columns
populated, that defaults are deterministic, that kwargs override, and that ``UNIQUE``-bound
fields differ across calls.
"""

from __future__ import annotations

from lengua_core.models import GeneratedCard
from tests.factories import (
    DEMO_USER_ID,
    make_card,
    make_generated_card,
    make_language,
    make_llm_budget,
    make_llm_usage,
    make_profile,
    make_review,
)


def test_make_profile_populates_required_fields() -> None:
    profile = make_profile()
    # profiles.id is the PK (FK to auth.users) — required.
    assert profile["id"] == DEMO_USER_ID
    assert profile["plan"]  # NOT NULL default 'free'


def test_make_language_populates_required_fields() -> None:
    lang = make_language()
    # languages: user_id + name are NOT NULL with no default.
    assert lang["user_id"] == DEMO_USER_ID
    assert lang["name"]


def test_make_card_populates_required_fields() -> None:
    card = make_card()
    # cards: user_id, language_id, front, back are NOT NULL with no default.
    for key in ("user_id", "language_id", "front", "back"):
        assert card[key] not in (None, ""), key
    # Defaults to a saved, due card so the review deck is non-empty.
    assert card["saved"] is True
    assert card["due"] is not None
    assert card["direction"] in ("recognition", "production")


def test_make_review_populates_required_fields() -> None:
    review = make_review()
    # reviews: user_id, card_id, rating are NOT NULL with no default.
    assert review["user_id"] == DEMO_USER_ID
    assert review["card_id"]
    assert review["rating"] in (1, 2, 3, 4)


def test_make_generated_card_populates_required_fields() -> None:
    card = make_generated_card()
    assert isinstance(card, GeneratedCard)
    assert card.sentence
    assert card.translation
    assert card.used_words  # non-empty list of used vocab words
    assert card.word_notes[0].word


def test_make_llm_usage_populates_required_fields() -> None:
    usage = make_llm_usage()
    # llm_usage PK is (user_id, day, kind); count defaults to 0.
    assert usage["user_id"] == DEMO_USER_ID
    assert usage["kind"] == "generate"
    assert usage["day"] is not None
    assert usage["count"] == 0


def test_make_llm_budget_populates_required_fields() -> None:
    budget = make_llm_budget()
    # llm_budget PK is (day); count defaults to 0.
    assert budget["day"] is not None
    assert budget["count"] == 0
    assert "user_id" not in budget  # global table — no per-user column


def test_defaults_are_deterministic() -> None:
    # Same explicit name (bypassing the unique counter) → identical dicts.
    assert make_card() == make_card()
    assert make_profile() == make_profile()
    assert make_language(name="Spanish") == make_language(name="Spanish")
    assert make_generated_card() == make_generated_card()


def test_overrides_apply() -> None:
    assert make_card(saved=False)["saved"] is False
    assert make_card(front="custom")["front"] == "custom"
    assert make_language(code="he")["code"] == "he"
    assert make_review(rating=1)["rating"] == 1
    assert make_profile(plan="pro")["plan"] == "pro"
    assert make_generated_card(sentence="x").sentence == "x"
    assert make_llm_usage(kind="discover", count=4)["kind"] == "discover"
    assert make_llm_usage(count=4)["count"] == 4
    assert make_llm_budget(count=9)["count"] == 9


def test_language_name_is_unique_per_call() -> None:
    # languages has UNIQUE (user_id, name) — default names must not collide.
    names = {make_language()["name"] for _ in range(5)}
    assert len(names) == 5
