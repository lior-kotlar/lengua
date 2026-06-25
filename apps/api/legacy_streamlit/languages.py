"""CRUD for learned languages and the persistent 'active language' setting (legacy app)."""
import sqlite3

from .db import connect

ACTIVE_KEY = "active_language_id"


def list_languages() -> list[sqlite3.Row]:
    with connect() as conn:
        return conn.execute(
            "SELECT * FROM languages ORDER BY name"
        ).fetchall()


def add_language(name: str, code: str | None = None, vowelized: bool = False) -> int:
    name = name.strip()
    with connect() as conn:
        cur = conn.execute(
            "INSERT OR IGNORE INTO languages (name, code, vowelized) VALUES (?, ?, ?)",
            (name, (code or "").strip() or None, 1 if vowelized else 0),
        )
        if cur.lastrowid and cur.rowcount:
            lang_id = cur.lastrowid
        else:  # already existed
            lang_id = conn.execute(
                "SELECT id FROM languages WHERE name = ?", (name,)
            ).fetchone()["id"]
        # Make it active if no active language is set yet.
        existing = conn.execute(
            "SELECT value FROM settings WHERE key = ?", (ACTIVE_KEY,)
        ).fetchone()
        if existing is None:
            conn.execute(
                "INSERT INTO settings (key, value) VALUES (?, ?)",
                (ACTIVE_KEY, str(lang_id)),
            )
    return lang_id


def delete_language(language_id: int) -> None:
    with connect() as conn:
        conn.execute("DELETE FROM languages WHERE id = ?", (language_id,))
        active = conn.execute(
            "SELECT value FROM settings WHERE key = ?", (ACTIVE_KEY,)
        ).fetchone()
        if active and active["value"] == str(language_id):
            conn.execute("DELETE FROM settings WHERE key = ?", (ACTIVE_KEY,))


def get_active_language_id() -> int | None:
    with connect() as conn:
        row = conn.execute(
            "SELECT value FROM settings WHERE key = ?", (ACTIVE_KEY,)
        ).fetchone()
    return int(row["value"]) if row and row["value"] else None


def set_active_language_id(language_id: int) -> None:
    with connect() as conn:
        conn.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (ACTIVE_KEY, str(language_id)),
        )


def set_vowelized(language_id: int, value: bool) -> None:
    with connect() as conn:
        conn.execute(
            "UPDATE languages SET vowelized = ? WHERE id = ?",
            (1 if value else 0, language_id),
        )


def get_language(language_id: int) -> sqlite3.Row | None:
    with connect() as conn:
        return conn.execute(
            "SELECT * FROM languages WHERE id = ?", (language_id,)
        ).fetchone()
