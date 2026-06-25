"""Tests for the E2E seed script (task 0.4.4).

Integration-marked — skipped when the Supabase stack (DB + Auth) is unreachable. Asserts the
seed produces the demo account (auth user → trigger-made profile) and a non-empty due-card set,
and that it is idempotent.
"""

from __future__ import annotations

import psycopg
import pytest

from scripts.seed_e2e import DEMO_EMAIL, SeedResult, seed
from tests.conftest import database_url

pytestmark = pytest.mark.integration


def test_seed_creates_demo_account_and_cards(demo_account: SeedResult) -> None:
    """The seed yields a demo user, a language, and a non-empty card set."""
    assert demo_account.user_id
    assert demo_account.language_id
    assert demo_account.card_count > 0  # non-empty review deck


def test_seed_demo_profile_exists_in_db(demo_account: SeedResult) -> None:
    """The trigger-created ``profiles`` row and the demo auth user are present and linked."""
    with psycopg.connect(database_url()) as conn:
        profile = conn.execute(
            "SELECT id FROM profiles WHERE id = %s", (demo_account.user_id,)
        ).fetchone()
        assert profile is not None, "handle_new_user trigger should have made the profile"

        auth_user = conn.execute(
            "SELECT email FROM auth.users WHERE id = %s", (demo_account.user_id,)
        ).fetchone()
        assert auth_user is not None and auth_user[0] == DEMO_EMAIL


def test_seed_cards_are_due_and_saved(demo_account: SeedResult) -> None:
    """The seeded cards are saved and due now (so they show up in the review queue)."""
    with psycopg.connect(database_url()) as conn:
        due_count = conn.execute(
            "SELECT count(*) FROM cards WHERE user_id = %s AND saved = true AND due <= now()",
            (demo_account.user_id,),
        ).fetchone()
        assert due_count is not None
        assert due_count[0] > 0


def test_seed_is_idempotent(demo_account: SeedResult) -> None:
    """Re-running the seed returns the same user and does not duplicate cards."""
    second: SeedResult = seed()
    assert second.user_id == demo_account.user_id
    assert second.language_id == demo_account.language_id
    assert second.card_count == demo_account.card_count
