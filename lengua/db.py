"""SQLite connection helper and schema initialization."""
import sqlite3
from contextlib import contextmanager

from . import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS languages (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL UNIQUE,
    code        TEXT,
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    vowelized   INTEGER NOT NULL DEFAULT 0  -- request harakat/nikkud in generated sentences
);

CREATE TABLE IF NOT EXISTS settings (
    key    TEXT PRIMARY KEY,
    value  TEXT
);

-- Every generated sentence. Phase 1 displays `front`; `back` (translation) is
-- stored hidden so Phase 2 flashcards are free. `saved` marks a card as added to
-- the review deck. `fsrs_state` holds fsrs.Card.to_dict() as JSON; `due` is the
-- denormalized due timestamp (ISO 8601) used to query the daily batch.
CREATE TABLE IF NOT EXISTS cards (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    language_id INTEGER NOT NULL REFERENCES languages(id) ON DELETE CASCADE,
    front       TEXT NOT NULL,
    back        TEXT NOT NULL,
    used_words  TEXT,                 -- JSON list
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    saved       INTEGER NOT NULL DEFAULT 0,
    fsrs_state  TEXT,                 -- JSON of fsrs.Card.to_dict(), null until saved
    due         TEXT,                 -- ISO 8601 due datetime, null until saved
    direction   TEXT,                 -- 'recognition' (target->EN) or 'production' (EN->target)
    word_explanations TEXT,           -- JSON {bare_word: note} for tap-a-word, null until generated
    gen_level   REAL                  -- continuous CEFR score the card was generated at, null if unknown
);

CREATE INDEX IF NOT EXISTS idx_cards_due
    ON cards(language_id, saved, due);

CREATE TABLE IF NOT EXISTS reviews (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    card_id     INTEGER NOT NULL REFERENCES cards(id) ON DELETE CASCADE,
    rating      INTEGER NOT NULL,     -- fsrs.Rating value 1-4
    reviewed_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- The learner's level per language as a continuous CEFR score (0..6). No user table
-- yet, so user_id defaults to a single learner; the column is here so multi-user
-- support arrives without a migration.
CREATE TABLE IF NOT EXISTS proficiency (
    user_id     INTEGER NOT NULL DEFAULT 1,
    language_id INTEGER NOT NULL REFERENCES languages(id) ON DELETE CASCADE,
    score       REAL NOT NULL DEFAULT 0.0,
    updated_at  TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (user_id, language_id)
);
"""


def get_connection() -> sqlite3.Connection:
    config.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def connect():
    """Yield a connection, commit on success, always close."""
    conn = get_connection()
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def _migrate(conn: sqlite3.Connection) -> None:
    """Apply column additions to pre-existing databases (idempotent)."""
    card_cols = {r["name"] for r in conn.execute("PRAGMA table_info(cards)")}
    if "direction" not in card_cols:
        conn.execute("ALTER TABLE cards ADD COLUMN direction TEXT")
    if "word_explanations" not in card_cols:
        conn.execute("ALTER TABLE cards ADD COLUMN word_explanations TEXT")
    if "gen_level" not in card_cols:
        # Continuous CEFR score the card was generated at; NULL for legacy/imported cards.
        conn.execute("ALTER TABLE cards ADD COLUMN gen_level REAL")

    lang_cols = {r["name"] for r in conn.execute("PRAGMA table_info(languages)")}
    if "vowelized" not in lang_cols:
        conn.execute(
            "ALTER TABLE languages ADD COLUMN vowelized INTEGER NOT NULL DEFAULT 0"
        )


def init_db() -> None:
    with connect() as conn:
        conn.executescript(SCHEMA)
        _migrate(conn)
