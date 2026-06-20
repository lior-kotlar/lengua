"""App configuration: loads .env, exposes paths and model settings."""
import os
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")

# Gemini
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

# Storage
DATA_DIR = PROJECT_ROOT / "data"
DB_PATH = Path(os.getenv("LENGUA_DB_PATH", DATA_DIR / "lengua.db"))

# Daily review batch
DAILY_NEW_LIMIT = int(os.getenv("LENGUA_DAILY_NEW_LIMIT", "10"))
DAILY_TOTAL_LIMIT = int(os.getenv("LENGUA_DAILY_TOTAL_LIMIT", "50"))

# Proficiency / level
# The learner's level per language is a continuous score on the CEFR scale (0..6);
# the band is CEFR_BANDS[floor(score)]. There is no user table yet, so state is keyed
# by (DEFAULT_USER_ID, language_id) — multi-user lands later with no migration.
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
