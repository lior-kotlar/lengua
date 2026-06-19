#!/usr/bin/env python3
"""
Import Arabic flashcards from an Anki collection into Lengua.

Two modes:
  --private   Read from AnkiDroid's private app-data collection (newer format,
              your personal Arabic↔Hebrew/English deck).  [default]
  --public    Read from the public AnkiDroid folder (older bulk-imported decks).

Usage:
    python scripts/import_anki.py [--private|--public] [--dry-run] [path/to/collection.anki2]

Scheduling is preserved:
  - Anki Review cards → FSRS Review state, stability ≈ interval, due date kept.
  - Anki New / Learning → fresh FSRS card, due now (paced at DAILY_NEW_LIMIT/day).

The phone database is opened READ-ONLY (copied locally first via MTP).
Nothing on the device is touched.
"""
import json
import re
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from lengua.db import connect, init_db
from lengua.languages import add_language

# ── paths ────────────────────────────────────────────────────────────────────
PRIVATE_DB = Path(r"C:\Users\liork\AppData\Local\Temp\anki_import\private_collection.anki2")
PUBLIC_DB  = Path(r"C:\Users\liork\AppData\Local\Temp\anki_import\collection.anki2")

LANGUAGE_NAME = "Levantine Arabic"
LANGUAGE_CODE = "ar"

# The personal "Arabic" deck in the private collection, plus its temp filtered copy.
PRIVATE_ARABIC_DIDS = {1756764905159, 1757001411411}

# The "Language Learning" model used in the public bulk-imported decks.
PUBLIC_LL_MODEL_ID = "1571322248393"

# ── FSRS helpers ─────────────────────────────────────────────────────────────

def strip_html(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text).strip()


def anki_factor_to_fsrs_difficulty(factor: int) -> float:
    """Map Anki ease factor (1300–3500) to FSRS difficulty (1=easy, 10=hard)."""
    if factor <= 0:
        return 5.0
    difficulty = 10.0 - (factor - 1300) / (3500 - 1300) * 9.0
    return round(max(1.0, min(10.0, difficulty)), 2)


def make_fsrs_state(card_type: int, card_due: int, card_ivl: int,
                    card_factor: int, col_crt: int) -> tuple[str, str]:
    """Return (fsrs_state_json, due_iso) from Anki card fields."""
    now = datetime.now(timezone.utc)

    if card_type in (0, 1):
        state: dict = {
            "card_id": 0, "state": 1, "step": 0,
            "stability": None, "difficulty": None,
            "due": now.isoformat(), "last_review": None,
        }
        return json.dumps(state), now.isoformat()

    # Review (type=2) or Relearning (type=3)
    # Anki due days are relative to col_crt, but col_crt may not be at midnight UTC.
    # Convert to the calendar date and use midnight UTC so that cards due "today"
    # in Anki become available at the start of that calendar day, not at the
    # potentially-odd hour when col_crt happens to fall.
    raw_ts = col_crt + card_due * 86400
    cal_date = datetime.fromtimestamp(raw_ts, tz=timezone.utc).date()
    due_dt = datetime(cal_date.year, cal_date.month, cal_date.day, tzinfo=timezone.utc)
    ivl = max(1, card_ivl)
    last_review_dt = due_dt - timedelta(days=ivl)
    state = {
        "card_id": 0, "state": 2, "step": 0,
        "stability": float(ivl),
        "difficulty": anki_factor_to_fsrs_difficulty(card_factor),
        "due": due_dt.isoformat(),
        "last_review": last_review_dt.isoformat(),
    }
    return json.dumps(state), due_dt.isoformat()


# ── import: private collection ───────────────────────────────────────────────

def import_private(anki_db: Path, dry_run: bool = False) -> None:
    """Import from the private AnkiDroid app-data collection (personal deck)."""
    if not anki_db.exists():
        sys.exit(f"Private Anki database not found: {anki_db}")

    init_db()
    anki = sqlite3.connect(f"file:{anki_db}?mode=ro", uri=True)
    anki.row_factory = sqlite3.Row

    col     = anki.execute("SELECT * FROM col").fetchone()
    col_crt = col["crt"]
    print(f"Collection epoch : {datetime.fromtimestamp(col_crt, tz=timezone.utc).date()}")

    # Build notetype field map  {ntid: [field_name, ...]}
    nt_fields: dict[int, list[str]] = {}
    for r in anki.execute("SELECT ntid, name FROM fields ORDER BY ntid, ord"):
        nt_fields.setdefault(r["ntid"], []).append(r["name"])

    # Fetch all cards whose note has at least one card in the Arabic decks
    did_placeholders = ",".join("?" * len(PRIVATE_ARABIC_DIDS))
    rows = anki.execute(
        f"""
        SELECT  c.id AS cid, c.nid, c.did, c.ord, c.type,
                CASE WHEN c.odid != 0 THEN c.odue ELSE c.due END AS due,
                c.ivl, c.factor, c.reps, c.lapses, c.odid,
                n.flds, n.mid, n.tags
        FROM    cards  c
        JOIN    notes  n ON n.id = c.nid
        WHERE   n.id IN (
                    SELECT DISTINCT nid FROM cards WHERE did IN ({did_placeholders})
                )
        ORDER BY n.id, c.ord
        """,
        list(PRIVATE_ARABIC_DIDS),
    ).fetchall()

    print(f"Total cards found: {len(rows)}")
    type_counts: dict[int, int] = {}
    for r in rows:
        type_counts[r["type"]] = type_counts.get(r["type"], 0) + 1
    labels = {0: "New", 1: "Learning", 2: "Review", 3: "Relearning"}
    for t, cnt in sorted(type_counts.items()):
        print(f"  type={t} ({labels.get(t,'?')}): {cnt}")

    if dry_run:
        print("\n-- DRY RUN sample (first 6) --")
        for row in rows[:6]:
            fields = row["flds"].split("\x1f")
            f0 = strip_html(fields[0]) if len(fields) > 0 else ""
            f1 = strip_html(fields[1]) if len(fields) > 1 else ""
            direction = "recognition" if row["ord"] == 0 else "production"
            _, due_iso = make_fsrs_state(row["type"], row["due"], row["ivl"], row["factor"], col_crt)
            print(
                f"\n  ord={row['ord']} dir={direction} type={row['type']} "
                f"ivl={row['ivl']} due={due_iso[:10]}"
            )
            print(f"    F0 (Arabic side): {f0[:70]}")
            print(f"    F1 (translation): {f1[:70]}")
        print("\nRe-run without --dry-run to write to the database.")
        anki.close()
        return

    lang_id = add_language(LANGUAGE_NAME, LANGUAGE_CODE, vowelized=True)
    print(f"Language '{LANGUAGE_NAME}' id={lang_id}")

    _check_existing_and_confirm(lang_id)

    skipped = imported = 0
    with connect() as conn:
        for row in rows:
            fields = row["flds"].split("\x1f")
            f0 = strip_html(fields[0]) if len(fields) > 0 else ""
            f1 = strip_html(fields[1]) if len(fields) > 1 else ""

            if not f0 or not f1:
                skipped += 1
                continue

            # ord=0 → recognition (F0=Arabic on front, F1=translation on back)
            # ord=1 → production  (F1=translation on front, F0=Arabic on back)
            if row["ord"] == 0:
                front, back, direction = f0, f1, "recognition"
            else:
                front, back, direction = f1, f0, "production"

            fsrs_state, due_iso = make_fsrs_state(
                row["type"], row["due"], row["ivl"], row["factor"], col_crt
            )

            conn.execute(
                "INSERT INTO cards "
                "(language_id, front, back, used_words, saved, fsrs_state, due, direction) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (lang_id, front, back, "[]", 1, fsrs_state, due_iso, direction),
            )
            imported += 1

    print(f"Imported : {imported} cards")
    if skipped:
        print(f"Skipped  : {skipped} (empty front or back)")
    anki.close()


# ── import: public collection ────────────────────────────────────────────────

def import_public(anki_db: Path, dry_run: bool = False) -> None:
    """Import from the public AnkiDroid folder (bulk 'Language Learning' decks)."""
    if not anki_db.exists():
        sys.exit(f"Public Anki database not found: {anki_db}")

    init_db()
    anki = sqlite3.connect(f"file:{anki_db}?mode=ro", uri=True)
    anki.row_factory = sqlite3.Row

    col     = anki.execute("SELECT * FROM col").fetchone()
    col_crt = col["crt"]
    decks   = json.loads(col["decks"])

    arabic_dids = [did for did, d in decks.items() if "Arabic" in d["name"]]
    print(f"Arabic sub-decks : {len(arabic_dids)}")

    placeholders = ",".join("?" * len(arabic_dids))
    rows = anki.execute(
        f"""
        SELECT  c.id AS cid, c.nid, c.did, c.ord, c.type, c.due, c.ivl,
                c.factor, n.flds
        FROM    cards  c
        JOIN    notes  n ON n.id = c.nid
        WHERE   n.mid = ? AND c.did IN ({placeholders})
        ORDER BY c.nid, c.ord
        """,
        [PUBLIC_LL_MODEL_ID] + arabic_dids,
    ).fetchall()

    print(f"Total Arabic cards: {len(rows)}")
    F_FRONT, F_BACK = 4, 5

    if dry_run:
        print("DRY RUN — not writing")
        anki.close()
        return

    lang_id = add_language(LANGUAGE_NAME, LANGUAGE_CODE, vowelized=True)
    _check_existing_and_confirm(lang_id)

    skipped = imported = 0
    with connect() as conn:
        for row in rows:
            fields  = row["flds"].split("\x1f")
            english = strip_html(fields[F_FRONT]) if len(fields) > F_FRONT else ""
            arabic  = strip_html(fields[F_BACK])  if len(fields) > F_BACK  else ""
            if not english or not arabic:
                skipped += 1
                continue
            direction = "production" if row["ord"] == 0 else "recognition"
            front     = english if row["ord"] == 0 else arabic
            back      = arabic  if row["ord"] == 0 else english
            fsrs_state, due_iso = make_fsrs_state(
                row["type"], row["due"], row["ivl"], row["factor"], col_crt
            )
            conn.execute(
                "INSERT INTO cards "
                "(language_id, front, back, used_words, saved, fsrs_state, due, direction) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (lang_id, front, back, "[]", 1, fsrs_state, due_iso, direction),
            )
            imported += 1

    print(f"Imported : {imported} cards")
    if skipped:
        print(f"Skipped  : {skipped}")
    anki.close()


# ── shared helper ─────────────────────────────────────────────────────────────

def _check_existing_and_confirm(lang_id: int) -> None:
    with connect() as conn:
        existing = conn.execute(
            "SELECT COUNT(*) AS n FROM cards WHERE language_id = ?", (lang_id,)
        ).fetchone()["n"]
    if existing > 0:
        answer = input(
            f"\nWarning: {existing} cards already exist for '{LANGUAGE_NAME}'. "
            "Import anyway? [y/N] "
        ).strip().lower()
        if answer != "y":
            print("Aborted.")
            sys.exit(0)


# ── entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    args  = [a for a in sys.argv[1:] if not a.startswith("-")]
    flags = [a for a in sys.argv[1:] if a.startswith("-")]

    dry_run = "--dry-run" in flags
    mode    = "public" if "--public" in flags else "private"

    anki_db = Path(args[0]) if args else (PRIVATE_DB if mode == "private" else PUBLIC_DB)

    if mode == "private":
        import_private(anki_db, dry_run)
    else:
        import_public(anki_db, dry_run)
