"""Pure, non-secret domain constants.

This module holds only **non-secret tuning constants**: the CEFR/level-adaptation
parameters used by :mod:`lengua_core.proficiency`, the legacy review-batch limits, and the
legacy SQLite database path used by the Streamlit app.

It intentionally contains **no secrets and no ``.env`` loading**. Provider keys/models and
all typed application configuration live in :class:`app.settings.Settings`
(``pydantic-settings``, read from the environment). Keeping this module free of secrets and
side effects keeps the domain core pure and safe to import from unit tests.
"""

from __future__ import annotations

import os
from pathlib import Path

# ── Legacy storage (used only by the legacy Streamlit app's SQLite store) ──────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
DB_PATH = Path(os.getenv("LENGUA_DB_PATH", str(DATA_DIR / "lengua.db")))

# ── Daily review batch (legacy defaults; per-user settings override these) ──────────
DAILY_NEW_LIMIT = int(os.getenv("LENGUA_DAILY_NEW_LIMIT", "10"))
DAILY_TOTAL_LIMIT = int(os.getenv("LENGUA_DAILY_TOTAL_LIMIT", "50"))

# ── Proficiency / level ────────────────────────────────────────────────────────────
# The learner's level per language is a continuous score on the CEFR scale (0..6); the
# band is ``CEFR_BANDS[floor(score)]``. State is keyed by ``(user_id, language_id)``; the
# legacy app uses a single default user until real multi-tenancy lands in the API.
DEFAULT_USER_ID = 1
CEFR_BANDS = ["A1", "A2", "B1", "B2", "C1", "C2"]
LEVEL_MIN = 0.0
LEVEL_MAX = float(len(CEFR_BANDS))  # 6.0 — top of C2

# How far one review nudges the score, by fsrs.Rating (1=Again, 2=Hard, 3=Good, 4=Easy).
# Easy pushes up, Again/Hard pull down, Good drifts up slightly. Values are illustrative
# and tunable: at +0.03/Easy it takes ~33 recognition "Easy"s to advance one band.
LEVEL_DELTAS = {1: -0.04, 2: -0.015, 3: 0.005, 4: 0.03}
# Production cards (English->target) are harder, so success on them is stronger evidence
# of proficiency and a struggle is more expected: boost positive nudges, dampen penalties.
PROD_POS_WEIGHT = 1.5
PROD_NEG_WEIGHT = 0.5
# Only reviews whose card was generated within this many bands of the current score move
# it — so a backlog of old/easy or below-level (imported) cards can't inflate the level.
LEVEL_WINDOW = 1.0
