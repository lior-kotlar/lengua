"""E2E/demo seed: a reviewer/demo account + a non-empty card set in a fresh DB.

Reused by the Playwright stack and (later) store review. The minimal schema here is a
stand-in; Phase 1 points the same seed at the real Alembic-managed schema.
"""

from dataclasses import dataclass

from sqlalchemy import Engine, text

from tests.factories import make_card, make_language, make_user

DEMO_EMAIL = "demo@lengua.test"

_SCHEMA = (
    "CREATE TABLE IF NOT EXISTS profiles (id uuid primary key, email text not null)",
    "CREATE TABLE IF NOT EXISTS languages ("
    "id bigint primary key, user_id uuid not null, name text not null)",
    "CREATE TABLE IF NOT EXISTS cards ("
    "id bigint primary key, user_id uuid not null, language_id bigint not null, "
    "front text not null, back text not null)",
)


@dataclass
class DemoData:
    """Identifiers the seed produced, for tests and the E2E stack to assert against."""

    user_id: str
    email: str
    card_count: int


def seed_demo(engine: Engine, card_count: int = 5) -> DemoData:
    """Create the demo account, a language, and ``card_count`` cards in ``engine``'s DB."""
    user = make_user()
    language = make_language(user=user)
    cards = [make_card(language=language) for _ in range(card_count)]

    with engine.begin() as conn:
        for ddl in _SCHEMA:
            conn.execute(text(ddl))
        conn.execute(
            text("INSERT INTO profiles (id, email) VALUES (:id, :email)"),
            {"id": str(user.id), "email": DEMO_EMAIL},
        )
        conn.execute(
            text("INSERT INTO languages (id, user_id, name) VALUES (:id, :user_id, :name)"),
            {"id": language.id, "user_id": str(user.id), "name": language.name},
        )
        conn.execute(
            text(
                "INSERT INTO cards (id, user_id, language_id, front, back) "
                "VALUES (:id, :user_id, :language_id, :front, :back)"
            ),
            [
                {
                    "id": card.id,
                    "user_id": str(card.user_id),
                    "language_id": card.language_id,
                    "front": card.front,
                    "back": card.back,
                }
                for card in cards
            ],
        )
    return DemoData(user_id=str(user.id), email=DEMO_EMAIL, card_count=len(cards))
