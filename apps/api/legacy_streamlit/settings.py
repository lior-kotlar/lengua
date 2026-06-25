"""Typed accessors for user-configurable app settings stored in the settings table (legacy app).

All keys and defaults live here so no magic strings scatter elsewhere. Non-secret tuning
constants come from :mod:`lengua_core.config`; the DB takes precedence when a value has been
explicitly set by the user. The Gemini model is operator config read from the environment
(``GEMINI_MODEL``), not a DB-stored secret.
"""
import os

from lengua_core import config

from .db import get_setting, set_setting

_DAILY_NEW      = "daily_new_limit"
_DAILY_TOTAL    = "daily_total_limit"
_DISCOVER_COUNT = "discover_word_count"
_MODEL          = "gemini_model"


def daily_new_limit() -> int:
    return int(get_setting(_DAILY_NEW, str(config.DAILY_NEW_LIMIT)))

def daily_total_limit() -> int:
    return int(get_setting(_DAILY_TOTAL, str(config.DAILY_TOTAL_LIMIT)))

def discover_word_count() -> int:
    return int(get_setting(_DISCOVER_COUNT, "3"))

def gemini_model() -> str:
    return get_setting(_MODEL, os.getenv("GEMINI_MODEL", "gemini-2.5-flash"))


def set_daily_new_limit(n: int) -> None:
    set_setting(_DAILY_NEW, str(n))

def set_daily_total_limit(n: int) -> None:
    set_setting(_DAILY_TOTAL, str(n))

def set_discover_word_count(n: int) -> None:
    set_setting(_DISCOVER_COUNT, str(n))

def set_gemini_model(model: str) -> None:
    set_setting(_MODEL, model)
