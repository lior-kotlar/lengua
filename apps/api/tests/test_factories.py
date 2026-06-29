"""Tests for the domain entity builders."""

import uuid

from tests.factories import (
    Card,
    Language,
    Review,
    User,
    make_card,
    make_language,
    make_review,
    make_user,
)


def test_make_user_populates_required_fields() -> None:
    user = make_user()

    assert isinstance(user, User)
    assert isinstance(user.id, uuid.UUID)
    assert user.plan == "free"
    assert user.created_at is not None


def test_make_language_links_to_a_user() -> None:
    user = make_user()
    language = make_language(user=user)

    assert isinstance(language, Language)
    assert language.user_id == user.id
    assert language.name
    assert isinstance(language.id, int)


def test_make_language_creates_a_user_when_none_given() -> None:
    language = make_language()

    assert isinstance(language.user_id, uuid.UUID)


def test_make_card_is_referentially_consistent() -> None:
    language = make_language()
    card = make_card(language=language)

    assert isinstance(card, Card)
    assert card.language_id == language.id
    assert card.user_id == language.user_id
    assert card.front and card.back
    assert card.used_words


def test_make_card_creates_its_own_language_when_none_given() -> None:
    card = make_card()

    assert isinstance(card.user_id, uuid.UUID)
    assert isinstance(card.language_id, int)


def test_make_review_links_to_its_card_and_accepts_overrides() -> None:
    card = make_card()
    review = make_review(card=card, rating=4)

    assert isinstance(review, Review)
    assert review.card_id == card.id
    assert review.user_id == card.user_id
    assert review.rating == 4


def test_make_review_creates_its_own_card_when_none_given() -> None:
    review = make_review()

    assert 1 <= review.rating <= 4
    assert isinstance(review.card_id, int)


def test_ids_are_unique_across_builds() -> None:
    cards = [make_card() for _ in range(3)]
    assert len({card.id for card in cards}) == 3
