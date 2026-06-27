"""Unit tests for the Alembic migration-URL resolution precedence (task 6.6.3).

These are pure (no DB, no ``migrations/env.py`` import) — they pin the ``-x db_url=`` >
``-x env=`` > ``DATABASE_URL`` precedence and the per-environment variable mapping the CD
migrate jobs rely on (``staging`` → ``STAGING_DATABASE_URL``, ``prod`` → ``PROD_DATABASE_URL``,
``local`` → ``DATABASE_URL``).
"""

from __future__ import annotations

import pytest

from app.db.migration_url import resolve_migration_url

STAGING = "postgresql://u:p@staging.example/db"
PROD = "postgresql://u:p@prod.example/db"
DEFAULT = "postgresql://u:p@127.0.0.1:54322/postgres"
ENVIRON = {"STAGING_DATABASE_URL": STAGING, "PROD_DATABASE_URL": PROD}


def test_db_url_override_wins_over_env_and_default() -> None:
    # `-x db_url=` beats `-x env=` and the DATABASE_URL default, even when both are present.
    url = resolve_migration_url(
        {"db_url": "postgresql://explicit/db", "env": "staging"}, ENVIRON, DEFAULT
    )
    assert url == "postgresql://explicit/db"


@pytest.mark.parametrize(
    ("env", "expected"),
    [
        ("staging", STAGING),
        ("prod", PROD),
        ("production", PROD),  # alias
        ("local", DEFAULT),
        ("  Staging  ", STAGING),  # case-insensitive + trimmed
        ("PROD", PROD),
    ],
)
def test_env_selects_the_right_connection_string(env: str, expected: str) -> None:
    assert resolve_migration_url({"env": env}, ENVIRON, DEFAULT) == expected


def test_no_args_falls_back_to_default_database_url() -> None:
    assert resolve_migration_url({}, ENVIRON, DEFAULT) == DEFAULT


def test_unknown_env_raises() -> None:
    with pytest.raises(RuntimeError, match="Unknown `-x env=qa`"):
        resolve_migration_url({"env": "qa"}, ENVIRON, DEFAULT)


def test_env_with_missing_variable_raises() -> None:
    # `-x env=staging` but STAGING_DATABASE_URL is not set in the environment.
    with pytest.raises(RuntimeError, match="STAGING_DATABASE_URL"):
        resolve_migration_url({"env": "staging"}, {}, DEFAULT)


def test_env_local_with_empty_default_raises() -> None:
    with pytest.raises(RuntimeError, match="DATABASE_URL"):
        resolve_migration_url({"env": "local"}, ENVIRON, "")


def test_no_source_at_all_raises() -> None:
    with pytest.raises(RuntimeError, match="No database URL"):
        resolve_migration_url({}, {}, "")
