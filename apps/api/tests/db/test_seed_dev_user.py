"""Dev-user seed tests (task 1.4.4).

The fixed dev profile is the placeholder ``current_user`` until Phase 2. The literal verify runs
the seed against a fresh ``alembic upgrade head`` database and asserts exactly one profile with
the dev UUID, idempotently. A second integration test exercises the Supabase auth-backed path
(the FK to ``auth.users`` requires a backing auth user), and a unit test pins the dev UUID to the
factory default so they never drift.
"""

from __future__ import annotations

import psycopg
import pytest

from scripts.seed_dev_user import DEV_EMAIL, DEV_USER_ID, seed_dev_user
from tests import factories
from tests.conftest import database_url
from tests.db.alembic_helpers import run_alembic, throwaway_database


def _profiles_with_id(url: str, user_id: str) -> int:
    with psycopg.connect(url) as conn:
        row = conn.execute("SELECT count(*) FROM profiles WHERE id = %s", (user_id,)).fetchone()
    assert row is not None
    return int(row[0])


def _total_profiles(url: str) -> int:
    with psycopg.connect(url) as conn:
        row = conn.execute("SELECT count(*) FROM profiles").fetchone()
    assert row is not None
    return int(row[0])


def test_dev_user_id_matches_factory_default() -> None:
    """The dev UUID equals ``factories.DEMO_USER_ID`` so factory rows line up with current_user."""
    assert DEV_USER_ID == factories.DEMO_USER_ID


@pytest.mark.integration
def test_seed_dev_user_idempotent_on_fresh_alembic_db() -> None:
    """On a fresh ``alembic upgrade head`` DB the seed yields exactly one dev profile, and
    re-running it leaves exactly one (the literal task verify)."""
    with throwaway_database() as url:
        run_alembic(url, "upgrade", "head")

        assert seed_dev_user(url) == DEV_USER_ID
        assert _profiles_with_id(url, DEV_USER_ID) == 1
        assert _total_profiles(url) == 1

        # Idempotent: a second run does not duplicate the row.
        assert seed_dev_user(url) == DEV_USER_ID
        assert _profiles_with_id(url, DEV_USER_ID) == 1
        assert _total_profiles(url) == 1


@pytest.mark.integration
def test_seed_dev_user_on_supabase_is_auth_backed() -> None:
    """Against Supabase (``profiles.id`` → ``auth.users``) the seed first creates the backing
    auth user with the same fixed id, then the dev profile — idempotently."""
    assert seed_dev_user() == DEV_USER_ID

    with psycopg.connect(database_url()) as conn:
        profile = conn.execute(
            "SELECT count(*) FROM profiles WHERE id = %s", (DEV_USER_ID,)
        ).fetchone()
        assert profile is not None and profile[0] == 1

        auth_user = conn.execute(
            "SELECT email FROM auth.users WHERE id = %s", (DEV_USER_ID,)
        ).fetchone()
        assert auth_user is not None and auth_user[0] == DEV_EMAIL

    # Idempotent re-run: still exactly one dev profile.
    assert seed_dev_user() == DEV_USER_ID
    with psycopg.connect(database_url()) as conn:
        profile = conn.execute(
            "SELECT count(*) FROM profiles WHERE id = %s", (DEV_USER_ID,)
        ).fetchone()
        assert profile is not None and profile[0] == 1
