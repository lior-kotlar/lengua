"""Verifies the E2E seed produces the demo account and a non-empty card set.

Skips automatically when Docker isn't available (see conftest.postgres_url).
"""

from sqlalchemy import Engine, text

from tests.seed import DEMO_EMAIL, DemoData, seed_demo


def test_seed_demo_creates_account_and_cards(db_engine: Engine) -> None:
    data = seed_demo(db_engine, card_count=4)

    with db_engine.connect() as conn:
        email = conn.execute(
            text("SELECT email FROM profiles WHERE id = :id"), {"id": data.user_id}
        ).scalar_one()
        card_total = conn.execute(
            text("SELECT count(*) FROM cards WHERE user_id = :id"), {"id": data.user_id}
        ).scalar_one()

    assert email == DEMO_EMAIL
    assert card_total == 4
    assert data.card_count == 4


def test_demo_account_fixture_is_seeded(demo_account: DemoData) -> None:
    assert demo_account.email == DEMO_EMAIL
    assert demo_account.card_count > 0
