"""Import the operator's legacy SQLite history into the multi-tenant Postgres schema (task 2.7).

A one-off **admin** migration. It reads the legacy single-user SQLite database (default the
operator's ``apps/api/data/lengua.db``) and inserts every ``languages`` / ``cards`` / ``reviews``
/ ``proficiency`` / ``settings`` row under **one** target ``user_id`` (the operator's Supabase
account UUID, passed on the CLI) in the new schema — preserving ``fsrs_state``, ``due``,
``saved``, and the proficiency scores so no review history is lost.

Why a privileged connection (not the request-path ``get_db``): RLS (Phase 2.6) now makes the
request-path session run as the non-privileged ``authenticated`` role, which can only touch
``auth.uid()``'s own rows. Seeding *another* user's rows is exactly what RLS blocks, so this
script connects as the ``postgres`` superuser via ``DATABASE_URL`` (RLS-exempt) — the same
privileged-connection rule the migrations and seed scripts follow.

Schema mapping (old → new):

- the global integer ``languages.id`` / ``cards.id`` are **remapped** to the new
  ``bigint generated always as identity`` ids (captured via ``RETURNING``) rather than forced in,
  so the import never collides with rows the account already created through the app, and the
  identity sequences stay consistent;
- every row is stamped with the target ``user_id`` (the legacy ``proficiency.user_id`` integer is
  ignored — there was only ever one learner);
- JSON-text columns (``used_words`` / ``word_explanations`` / ``fsrs_state``) become ``jsonb`` and
  ISO-8601 text (``due`` / ``created_at`` / ``reviewed_at``) becomes ``timestamptz``;
- the legacy global ``settings`` key/values become the user's ``user_settings`` rows.

Idempotency (task 2.7.2): every table is guarded by a natural key — ``languages`` on
``(user_id, name)``, ``cards`` on ``(user_id, language_id, front, back, direction)``, ``reviews``
on ``(user_id, card_id, rating, reviewed_at)``, and the composite-PK ``proficiency`` /
``user_settings`` — so re-running inserts nothing new (same final row counts, no duplicates).
``--dry-run`` runs the whole import inside a transaction that is **rolled back**, writing nothing
while reporting the rows it *would* insert.

Usage::

    uv run python scripts/import_sqlite.py --user-id <UUID> \
        [--sqlite-path data/lengua.db] [--database-url postgresql://...] [--dry-run]
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import psycopg
from psycopg.types.json import Json

# Default the operator's real SQLite DB (apps/api/data/lengua.db) and the local Supabase CLI DSN;
# both are overridable on the CLI / via DATABASE_URL for a throwaway or hosted Postgres.
DEFAULT_SQLITE_PATH = Path(__file__).resolve().parent.parent / "data" / "lengua.db"
DEFAULT_DATABASE_URL = "postgresql://postgres:postgres@127.0.0.1:54322/postgres"


# ── Source (SQLite) read ────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class SourceData:
    """Every legacy row, ordered deterministically so id-remapping is stable across runs."""

    languages: list[dict[str, Any]]
    cards: list[dict[str, Any]]
    reviews: list[dict[str, Any]]
    proficiency: list[dict[str, Any]]
    settings: list[dict[str, Any]]


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (name,)
    ).fetchone()
    return row is not None


def _rows(conn: sqlite3.Connection, table: str, order_by: str) -> list[dict[str, Any]]:
    """All rows of ``table`` as plain dicts (missing-column-safe), or ``[]`` if absent."""
    if not _table_exists(conn, table):
        return []
    cursor = conn.execute(f"SELECT * FROM {table} ORDER BY {order_by}")  # noqa: S608 — fixed names
    return [dict(row) for row in cursor.fetchall()]


def read_sqlite(path: Path) -> SourceData:
    """Read the legacy DB into memory. Tolerates an old schema that predates some columns."""
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        return SourceData(
            languages=_rows(conn, "languages", "id"),
            cards=_rows(conn, "cards", "id"),
            reviews=_rows(conn, "reviews", "id"),
            proficiency=_rows(conn, "proficiency", "language_id"),
            settings=_rows(conn, "settings", "key"),
        )
    finally:
        conn.close()


# ── Value coercion (SQLite text/int → Postgres jsonb/timestamptz/bool) ───────────────


def _json(value: Any) -> Json | None:
    """A JSON-text column → a ``jsonb`` adapter, or ``None`` for null/empty."""
    if value is None or value == "":
        return None
    return Json(json.loads(value) if isinstance(value, str) else value)


def _dt(value: Any) -> datetime | None:
    """An ISO-8601 / ``YYYY-MM-DD HH:MM:SS`` string → an aware datetime (UTC if naive)."""
    if not value:
        return None
    text = str(value).strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        parsed = datetime.fromisoformat(text.replace(" ", "T"))
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)


# ── Stats ────────────────────────────────────────────────────────────────────────────


@dataclass
class TableStat:
    """How many rows were inserted vs skipped (already present) for one table."""

    inserted: int = 0
    skipped: int = 0

    def record(self, *, inserted: bool) -> None:
        if inserted:
            self.inserted += 1
        else:
            self.skipped += 1


@dataclass
class ImportStats:
    """Per-table insert/skip tallies for the whole run."""

    languages: TableStat = field(default_factory=TableStat)
    cards: TableStat = field(default_factory=TableStat)
    reviews: TableStat = field(default_factory=TableStat)
    proficiency: TableStat = field(default_factory=TableStat)
    settings: TableStat = field(default_factory=TableStat)

    def items(self) -> list[tuple[str, TableStat]]:
        return [
            ("languages", self.languages),
            ("cards", self.cards),
            ("reviews", self.reviews),
            ("proficiency", self.proficiency),
            ("settings", self.settings),
        ]

    def total_inserted(self) -> int:
        return sum(stat.inserted for _, stat in self.items())

    def total_skipped(self) -> int:
        return sum(stat.skipped for _, stat in self.items())


# ── Target (Postgres) upserts — each idempotent on a natural key ─────────────────────


def ensure_profile(conn: psycopg.Connection, user_id: str) -> None:
    """Make sure ``profiles[user_id]`` exists so the child FKs hold.

    In real prod the account already exists (signup created the profile via the trigger), so
    this is a no-op. On a bare admin Postgres (no ``auth.users`` FK) the row is created directly.
    On Supabase with no backing auth user it surfaces a clear, actionable error rather than a raw
    FK violation.
    """
    if conn.execute("SELECT 1 FROM profiles WHERE id = %s", (user_id,)).fetchone() is not None:
        return
    try:
        conn.execute("INSERT INTO profiles (id) VALUES (%s)", (user_id,))
    except psycopg.errors.ForeignKeyViolation as exc:
        raise SystemExit(
            f"Target user {user_id} has no profile and no backing auth.users row; "
            "create the account (sign up) before importing."
        ) from exc


def _upsert_language(
    conn: psycopg.Connection, user_id: str, lang: dict[str, Any]
) -> tuple[int, bool]:
    """Insert the language (or reuse the existing one). Returns ``(target_id, inserted?)``."""
    inserted = conn.execute(
        "INSERT INTO languages (user_id, name, code, vowelized, created_at) "
        "VALUES (%s, %s, %s, %s, COALESCE(%s, now())) "
        "ON CONFLICT (user_id, name) DO NOTHING RETURNING id",
        (
            user_id,
            lang["name"],
            lang.get("code"),
            bool(lang.get("vowelized")),
            _dt(lang.get("created_at")),
        ),
    ).fetchone()
    if inserted is not None:
        return int(inserted[0]), True
    existing = conn.execute(
        "SELECT id FROM languages WHERE user_id = %s AND name = %s", (user_id, lang["name"])
    ).fetchone()
    assert existing is not None  # the conflict above guarantees the row is there
    return int(existing[0]), False


def _upsert_card(
    conn: psycopg.Connection, user_id: str, language_id: int, card: dict[str, Any]
) -> tuple[int, bool]:
    """Insert the card (or reuse it). Natural key: (user, language, front, back, direction)."""
    existing = conn.execute(
        "SELECT id FROM cards WHERE user_id = %s AND language_id = %s "
        "AND front = %s AND back = %s AND direction IS NOT DISTINCT FROM %s",
        (user_id, language_id, card["front"], card["back"], card.get("direction")),
    ).fetchone()
    if existing is not None:
        return int(existing[0]), False
    inserted = conn.execute(
        "INSERT INTO cards (user_id, language_id, front, back, used_words, direction, "
        "word_explanations, gen_level, saved, fsrs_state, due, created_at) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, COALESCE(%s, now())) RETURNING id",
        (
            user_id,
            language_id,
            card["front"],
            card["back"],
            _json(card.get("used_words")),
            card.get("direction"),
            _json(card.get("word_explanations")),
            card.get("gen_level"),
            bool(card.get("saved")),
            _json(card.get("fsrs_state")),
            _dt(card.get("due")),
            _dt(card.get("created_at")),
        ),
    ).fetchone()
    assert inserted is not None
    return int(inserted[0]), True


def _upsert_review(
    conn: psycopg.Connection, user_id: str, card_id: int, review: dict[str, Any]
) -> bool:
    """Insert a review unless an identical one (card, rating, timestamp) already exists."""
    reviewed_at = _dt(review.get("reviewed_at"))
    existing = conn.execute(
        "SELECT 1 FROM reviews WHERE user_id = %s AND card_id = %s AND rating = %s "
        "AND reviewed_at IS NOT DISTINCT FROM %s",
        (user_id, card_id, int(review["rating"]), reviewed_at),
    ).fetchone()
    if existing is not None:
        return False
    conn.execute(
        "INSERT INTO reviews (user_id, card_id, rating, reviewed_at) "
        "VALUES (%s, %s, %s, COALESCE(%s, now()))",
        (user_id, card_id, int(review["rating"]), reviewed_at),
    )
    return True


def _upsert_proficiency(
    conn: psycopg.Connection, user_id: str, language_id: int, prof: dict[str, Any]
) -> bool:
    """Insert the per-language score (composite PK ``(user_id, language_id)``)."""
    existing = conn.execute(
        "SELECT 1 FROM proficiency WHERE user_id = %s AND language_id = %s",
        (user_id, language_id),
    ).fetchone()
    if existing is not None:
        return False
    conn.execute(
        "INSERT INTO proficiency (user_id, language_id, score, updated_at) "
        "VALUES (%s, %s, %s, COALESCE(%s, now()))",
        (user_id, language_id, float(prof["score"]), _dt(prof.get("updated_at"))),
    )
    return True


def _upsert_setting(conn: psycopg.Connection, user_id: str, setting: dict[str, Any]) -> bool:
    """Insert a legacy global setting as a user setting (composite PK ``(user_id, key)``)."""
    existing = conn.execute(
        "SELECT 1 FROM user_settings WHERE user_id = %s AND key = %s",
        (user_id, setting["key"]),
    ).fetchone()
    if existing is not None:
        return False
    conn.execute(
        "INSERT INTO user_settings (user_id, key, value) VALUES (%s, %s, %s)",
        (user_id, setting["key"], setting.get("value")),
    )
    return True


def import_data(conn: psycopg.Connection, user_id: str, src: SourceData) -> ImportStats:
    """Insert the whole source graph under ``user_id``, remapping ids parent→child."""
    stats = ImportStats()

    lang_map: dict[int, int] = {}
    for lang in src.languages:
        target_id, inserted = _upsert_language(conn, user_id, lang)
        lang_map[int(lang["id"])] = target_id
        stats.languages.record(inserted=inserted)

    card_map: dict[int, int] = {}
    for card in src.cards:
        target_lang = lang_map.get(int(card["language_id"]))
        if target_lang is None:  # orphan card → no language; skip defensively
            continue
        target_id, inserted = _upsert_card(conn, user_id, target_lang, card)
        card_map[int(card["id"])] = target_id
        stats.cards.record(inserted=inserted)

    for review in src.reviews:
        target_card = card_map.get(int(review["card_id"]))
        if target_card is None:
            continue
        stats.reviews.record(inserted=_upsert_review(conn, user_id, target_card, review))

    for prof in src.proficiency:
        target_lang = lang_map.get(int(prof["language_id"]))
        if target_lang is None:
            continue
        stats.proficiency.record(inserted=_upsert_proficiency(conn, user_id, target_lang, prof))

    for setting in src.settings:
        stats.settings.record(inserted=_upsert_setting(conn, user_id, setting))

    return stats


def run_import(*, database_url: str, sqlite_path: Path, user_id: str, dry_run: bool) -> ImportStats:
    """Read the SQLite DB and import it under ``user_id``. ``dry_run`` rolls back (writes nothing).

    The whole import runs in one transaction so it is all-or-nothing; ``--dry-run`` rolls that
    transaction back, so the natural-key guards still dedup within the run while nothing persists.
    """
    src = read_sqlite(sqlite_path)
    conn = psycopg.connect(database_url)
    try:
        ensure_profile(conn, user_id)
        stats = import_data(conn, user_id, src)
        if dry_run:
            conn.rollback()
        else:
            conn.commit()
        return stats
    finally:
        conn.close()  # an open (errored) transaction is rolled back on close


# ── CLI ──────────────────────────────────────────────────────────────────────────────


def _print_report(stats: ImportStats, *, user_id: str, dry_run: bool) -> None:
    banner = "DRY RUN - no rows written" if dry_run else "IMPORT COMPLETE"
    print(f"\n=== {banner} - target user {user_id} ===")
    header = f"{'table':<14}{'inserted':>10}{'skipped':>10}"
    print(header)
    print("-" * len(header))
    for name, stat in stats.items():
        print(f"{name:<14}{stat.inserted:>10}{stat.skipped:>10}")
    print("-" * len(header))
    print(f"{'TOTAL':<14}{stats.total_inserted():>10}{stats.total_skipped():>10}")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Import legacy SQLite data into Postgres (2.7).")
    parser.add_argument(
        "--user-id", required=True, help="Target profile UUID (the operator's account)."
    )
    parser.add_argument(
        "--sqlite-path",
        default=str(DEFAULT_SQLITE_PATH),
        help=f"Source SQLite DB (default: {DEFAULT_SQLITE_PATH}).",
    )
    parser.add_argument(
        "--database-url",
        default=None,
        help="Target Postgres DSN (default: $DATABASE_URL or the local Supabase CLI DSN). "
        "Must be a PRIVILEGED (postgres) connection — RLS blocks cross-user inserts.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report planned inserts inside a rolled-back transaction; write nothing.",
    )
    args = parser.parse_args(argv)

    try:
        user_id = str(uuid.UUID(args.user_id))
    except ValueError:
        parser.error(f"--user-id must be a valid UUID, got {args.user_id!r}")

    sqlite_path = Path(args.sqlite_path)
    if not sqlite_path.exists():
        raise SystemExit(f"SQLite database not found: {sqlite_path}")

    database_url = args.database_url or os.getenv("DATABASE_URL") or DEFAULT_DATABASE_URL
    stats = run_import(
        database_url=database_url, sqlite_path=sqlite_path, user_id=user_id, dry_run=args.dry_run
    )
    _print_report(stats, user_id=user_id, dry_run=args.dry_run)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
