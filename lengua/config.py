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
