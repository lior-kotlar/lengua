"""Plain builder functions for test data (task 0.4.1).

These are **not** factory-boy factories: the SQLAlchemy models don't exist until Phase 1, so a
factory bound to a model class would have nothing to bind to. Instead each ``make_*`` returns a
plain ``dict`` whose keys are the column names of the corresponding table in
``supabase/migrations/20260621000000_initial_schema.sql`` — ready to be ``INSERT``ed by the DB
fixtures (0.4.3) and the seed script (0.4.4), or asserted on directly in unit tests.

Design contract:

- **Deterministic defaults** — no randomness, no wall-clock. A module-level counter
  (:func:`_next_seq`) supplies distinct values for fields under a ``UNIQUE`` constraint
  (e.g. ``languages.name``) so repeated calls don't collide, while staying reproducible within
  a process run.
- **kwargs-overridable** — any column can be overridden: ``make_card(saved=False)``.

:func:`make_generated_card` builds the LLM *output* model (:class:`GeneratedCard`), not a table
row — it's what a provider returns before it is persisted as two ``cards`` rows.
"""

from __future__ import annotations

import itertools
from datetime import UTC, datetime
from typing import Any

from app.repositories.cards import NewCard
from lengua_core.models import GeneratedCard, WordNote

# A fixed demo user id (a valid UUID). All ``user_id`` foreign keys default to this so a
# minimal graph (profile → language → card → review) wires up without the caller juggling ids.
DEMO_USER_ID = "00000000-0000-0000-0000-000000000001"

# A fixed instant used for every ``*_at`` / ``due`` default so timestamps are reproducible.
FIXED_NOW = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)

_seq = itertools.count(1)


def _next_seq() -> int:
    """Return the next value of a process-wide monotonic counter (deterministic per run)."""
    return next(_seq)


def make_profile(**overrides: Any) -> dict[str, Any]:
    """Build a ``profiles`` row (1:1 with an ``auth.users`` row).

    ``id`` is the user's UUID; it defaults to :data:`DEMO_USER_ID`.
    """
    row: dict[str, Any] = {
        "id": DEMO_USER_ID,
        "plan": "free",
        "created_at": FIXED_NOW,
    }
    row.update(overrides)
    return row


def make_language(**overrides: Any) -> dict[str, Any]:
    """Build a ``languages`` row. ``name`` is made unique per call to respect
    ``UNIQUE (user_id, name)``."""
    n = _next_seq()
    row: dict[str, Any] = {
        "user_id": DEMO_USER_ID,
        "name": f"Spanish {n}",
        "code": "es",
        "vowelized": False,
        "created_at": FIXED_NOW,
    }
    row.update(overrides)
    return row


def make_card(**overrides: Any) -> dict[str, Any]:
    """Build a ``cards`` row.

    Defaults to a *saved, due-now* recognition card (``saved=True``, ``due=FIXED_NOW``) so the
    seed/E2E fixtures get a non-empty review deck out of the box. ``language_id`` defaults to
    ``1`` (the first identity-generated language); override it with a real id when inserting.
    """
    row: dict[str, Any] = {
        "user_id": DEMO_USER_ID,
        "language_id": 1,
        "front": "Hola, ¿cómo estás?",
        "back": "Hello, how are you?",
        "used_words": ["hola"],
        "direction": "recognition",
        "word_explanations": None,
        "gen_level": 0.0,
        "saved": True,
        "fsrs_state": None,
        "due": FIXED_NOW,
        "created_at": FIXED_NOW,
    }
    row.update(overrides)
    return row


def make_review(**overrides: Any) -> dict[str, Any]:
    """Build a ``reviews`` row. ``rating`` defaults to ``3`` (Good); ``card_id`` to ``1``."""
    row: dict[str, Any] = {
        "user_id": DEMO_USER_ID,
        "card_id": 1,
        "rating": 3,  # 1=Again 2=Hard 3=Good 4=Easy
        "reviewed_at": FIXED_NOW,
    }
    row.update(overrides)
    return row


def make_generated_card(**overrides: Any) -> GeneratedCard:
    """Build a :class:`GeneratedCard` — the structured LLM output (pre-persistence)."""
    defaults: dict[str, Any] = {
        "sentence": "Hola, ¿cómo estás?",
        "translation": "Hello, how are you?",
        "used_words": ["hola"],
        "word_notes": [WordNote(word="hola", note="hola: a greeting.")],
    }
    defaults.update(overrides)
    return GeneratedCard(**defaults)


def make_new_card(**overrides: Any) -> NewCard:
    """Build a :class:`~app.repositories.cards.NewCard` — the repository's write contract.

    Defaults to a *saved, due-now* recognition card; override ``direction`` / ``fsrs_state`` /
    ``due`` etc. to craft new-vs-reviewed or unsaved cards in repository tests.
    """
    defaults: dict[str, Any] = {
        "front": "Hola, ¿cómo estás?",
        "back": "Hello, how are you?",
        "direction": "recognition",
        "used_words": ["hola"],
        "word_explanations": None,
        "gen_level": 0.0,
        "saved": True,
        "fsrs_state": None,
        "due": FIXED_NOW,
    }
    defaults.update(overrides)
    return NewCard(**defaults)
