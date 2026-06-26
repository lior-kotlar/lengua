"""Tests for the legacy SQLite → Postgres import (tasks 2.7.1 / 2.7.2).

Strategy: build a representative legacy SQLite DB (the real ``legacy_streamlit.db`` schema, with
two languages, saved+unsaved cards carrying real FSRS state, reviews, proficiency and settings),
create a throwaway target user on the Supabase-CLI Postgres (an ``auth.users`` insert fires the
``handle_new_user`` trigger that makes the ``profiles`` row), then run the importer against it.

We assert:

* **counts match the source** for languages/cards/reviews/proficiency (+ the user_settings the
  legacy ``settings`` table maps to), and a card's ``front``/``back``/``fsrs_state`` round-trips
  (2.7.1);
* **``--dry-run`` writes nothing** yet reports the planned inserts (2.7.2);
* **a second real import duplicates nothing** — same final counts, zero new inserts (2.7.2).

The DB tests are ``@pytest.mark.integration`` and auto-skip when Postgres is unreachable; the two
CLI-validation tests need no DB and always run.
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from collections.abc import Iterator
from typing import Any

import psycopg
import pytest
from fsrs import Rating

from legacy_streamlit.db import SCHEMA
from lengua_core.scheduler import apply_rating, new_card_state
from scripts.import_sqlite import ImportStats, main, run_import
from tests.conftest import _skip_if_db_unreachable, database_url

# Source-row counts the fixture below builds — the importer must reproduce these in Postgres.
SOURCE_COUNTS = {"languages": 2, "cards": 3, "reviews": 2, "proficiency": 2, "settings": 2}


@pytest.fixture(scope="module")
def source_db(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Any]:
    """Build a populated legacy SQLite DB; return its path, counts, and a card to spot-check."""
    path = tmp_path_factory.mktemp("import") / "lengua.db"
    new_state, new_due = new_card_state()
    reviewed_state, reviewed_due = apply_rating(new_state, Rating.Good)

    conn = sqlite3.connect(path)
    try:
        conn.executescript(SCHEMA)
        insert_lang = "INSERT INTO languages (id, name, code, vowelized) VALUES (?, ?, ?, ?)"
        conn.execute(insert_lang, (1, "Spanish", "es", 0))
        conn.execute(insert_lang, (2, "Hebrew", "he", 1))
        # Card 1: saved + reviewed (FSRS state carries a last_review) — the spot-check target.
        conn.execute(
            "INSERT INTO cards (id, language_id, front, back, used_words, saved, fsrs_state, due, "
            "direction, word_explanations, gen_level) VALUES (1, 1, ?, ?, ?, 1, ?, ?, ?, ?, 2.0)",
            (
                "Hola mundo",
                "Hello world",
                json.dumps(["hola", "mundo"]),
                reviewed_state,
                reviewed_due,
                "recognition",
                json.dumps({"hola": "hello"}),
            ),
        )
        # Card 2: saved + new (never reviewed).
        conn.execute(
            "INSERT INTO cards (id, language_id, front, back, used_words, saved, fsrs_state, due, "
            "direction, gen_level) VALUES (2, 1, ?, ?, ?, 1, ?, ?, ?, 2.0)",
            (
                "Hello world",
                "Hola mundo",
                json.dumps(["hola", "mundo"]),
                new_state,
                new_due,
                "production",
            ),
        )
        # Card 3: unsaved (no FSRS state / due) — a generated-but-not-added card.
        conn.execute(
            "INSERT INTO cards (id, language_id, front, back, used_words, saved, direction) "
            "VALUES (3, 2, ?, ?, ?, 0, ?)",
            ("Shalom", "Hello", json.dumps(["shalom"]), "recognition"),
        )
        # Two reviews of card 1 with distinct timestamps (the natural key dedups on re-import).
        insert_review = "INSERT INTO reviews (card_id, rating, reviewed_at) VALUES (?, ?, ?)"
        conn.execute(insert_review, (1, 3, "2026-01-01 10:00:00"))
        conn.execute(insert_review, (1, 4, "2026-01-02 11:30:00"))
        conn.execute("INSERT INTO proficiency (user_id, language_id, score) VALUES (1, 1, 1.75)")
        conn.execute("INSERT INTO proficiency (user_id, language_id, score) VALUES (1, 2, 0.5)")
        conn.execute("INSERT INTO settings (key, value) VALUES ('daily_new_limit', '7')")
        conn.execute("INSERT INTO settings (key, value) VALUES ('daily_total_limit', '40')")
        conn.commit()
    finally:
        conn.close()

    return {
        "path": path,
        "counts": dict(SOURCE_COUNTS),
        "spot_card": {
            "front": "Hola mundo",
            "back": "Hello world",
            "fsrs_state": json.loads(reviewed_state),
        },
    }


@pytest.fixture
def target_user() -> Iterator[str]:
    """A fresh throwaway account: insert ``auth.users`` (trigger makes ``profiles``), drop after."""
    _skip_if_db_unreachable()
    uid = uuid.uuid4()
    with psycopg.connect(database_url(), autocommit=True) as conn:
        conn.execute(
            "INSERT INTO auth.users (id, email) VALUES (%s, %s)",
            (uid, f"import-{uid.hex[:12]}@lengua.test"),
        )
    try:
        yield str(uid)
    finally:
        with psycopg.connect(database_url(), autocommit=True) as conn:
            conn.execute("DELETE FROM auth.users WHERE id = %s", (uid,))


def _counts(conn: psycopg.Connection, user_id: str) -> dict[str, int]:
    """Live Postgres row counts for one user across the imported tables."""

    def n(sql: str) -> int:
        row = conn.execute(sql, (user_id,)).fetchone()
        assert row is not None
        return int(row[0])

    return {
        "languages": n("SELECT count(*) FROM languages WHERE user_id = %s"),
        "cards": n("SELECT count(*) FROM cards WHERE user_id = %s"),
        "reviews": n("SELECT count(*) FROM reviews WHERE user_id = %s"),
        "proficiency": n("SELECT count(*) FROM proficiency WHERE user_id = %s"),
        "settings": n("SELECT count(*) FROM user_settings WHERE user_id = %s"),
    }


@pytest.mark.integration
def test_import_matches_source_counts(source_db: dict[str, Any], target_user: str) -> None:
    """A real import reproduces every source row under the target user and preserves card data."""
    run_import(
        database_url=database_url(),
        sqlite_path=source_db["path"],
        user_id=target_user,
        dry_run=False,
    )

    with psycopg.connect(database_url(), autocommit=True) as conn:
        assert _counts(conn, target_user) == source_db["counts"]

        spot = source_db["spot_card"]
        row = conn.execute(
            "SELECT back, fsrs_state, saved, direction FROM cards "
            "WHERE user_id = %s AND front = %s",
            (target_user, spot["front"]),
        ).fetchone()
        assert row is not None
        assert row[0] == spot["back"]
        assert row[1] == spot["fsrs_state"]  # jsonb round-trips to the same dict
        assert row[2] is True  # saved preserved
        assert row[3] == "recognition"

        # An unsaved card keeps its null FSRS state / due (not forced into the deck).
        unsaved = conn.execute(
            "SELECT saved, fsrs_state, due FROM cards WHERE user_id = %s AND front = %s",
            (target_user, "Shalom"),
        ).fetchone()
        assert unsaved == (False, None, None)

        # Proficiency scores are preserved exactly.
        scores = {
            float(r[0])
            for r in conn.execute(
                "SELECT score FROM proficiency WHERE user_id = %s", (target_user,)
            ).fetchall()
        }
        assert scores == {1.75, 0.5}


@pytest.mark.integration
def test_dry_run_writes_nothing(source_db: dict[str, Any], target_user: str) -> None:
    """``--dry-run`` reports the planned inserts but leaves the database empty."""
    stats = run_import(
        database_url=database_url(),
        sqlite_path=source_db["path"],
        user_id=target_user,
        dry_run=True,
    )

    with psycopg.connect(database_url(), autocommit=True) as conn:
        assert _counts(conn, target_user) == dict.fromkeys(source_db["counts"], 0)

    planned = {name: stat.inserted for name, stat in stats.items()}
    assert planned == source_db["counts"]
    assert stats.total_skipped() == 0


@pytest.mark.integration
def test_idempotent_double_import(source_db: dict[str, Any], target_user: str) -> None:
    """Running the real import twice yields the same final counts — no duplicate rows."""
    first = run_import(
        database_url=database_url(),
        sqlite_path=source_db["path"],
        user_id=target_user,
        dry_run=False,
    )
    second = run_import(
        database_url=database_url(),
        sqlite_path=source_db["path"],
        user_id=target_user,
        dry_run=False,
    )

    with psycopg.connect(database_url(), autocommit=True) as conn:
        assert _counts(conn, target_user) == source_db["counts"]

    assert first.total_inserted() == sum(source_db["counts"].values())
    assert second.total_inserted() == 0  # everything already present
    assert second.total_skipped() == sum(source_db["counts"].values())


@pytest.mark.integration
def test_cli_dry_run_writes_nothing(
    source_db: dict[str, Any], target_user: str, capsys: pytest.CaptureFixture[str]
) -> None:
    """The CLI entrypoint with ``--dry-run`` exits 0, prints the banner, and writes nothing."""
    rc = main(
        [
            "--user-id",
            target_user,
            "--sqlite-path",
            str(source_db["path"]),
            "--database-url",
            database_url(),
            "--dry-run",
        ]
    )
    assert rc == 0
    assert "DRY RUN" in capsys.readouterr().out

    with psycopg.connect(database_url(), autocommit=True) as conn:
        assert _counts(conn, target_user) == dict.fromkeys(source_db["counts"], 0)


def test_cli_rejects_a_non_uuid_user_id(source_db: dict[str, Any]) -> None:
    """A malformed ``--user-id`` is rejected before any DB connection (argparse error → exit 2)."""
    with pytest.raises(SystemExit) as exc:
        main(["--user-id", "not-a-uuid", "--sqlite-path", str(source_db["path"])])
    assert exc.value.code == 2


def test_cli_rejects_a_missing_sqlite_path() -> None:
    """A missing source DB fails fast with a clear error (no DB needed)."""
    bogus = uuid.uuid4()
    with pytest.raises(SystemExit) as exc:
        main(["--user-id", str(bogus), "--sqlite-path", "/no/such/lengua.db"])
    assert "not found" in str(exc.value)


def test_import_stats_tally() -> None:
    """``ImportStats`` aggregates inserted/skipped across tables (pure, no DB)."""
    stats = ImportStats()
    stats.languages.record(inserted=True)
    stats.cards.record(inserted=True)
    stats.cards.record(inserted=False)
    assert stats.total_inserted() == 2
    assert stats.total_skipped() == 1
