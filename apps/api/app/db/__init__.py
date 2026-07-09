"""Database layer: the declarative base, ORM models, and async session/engine wiring.

Importing this package registers every ORM model on :data:`Base.metadata`, so callers can rely
on ``from app.db import Base`` exposing the full schema (used by the metadata tests and, later,
by Alembic).
"""

from __future__ import annotations

from app.db.base import Base
from app.db.models import (
    Card,
    FeatureFlag,
    Language,
    LlmBudget,
    LlmUsage,
    Proficiency,
    Profile,
    PromptVersion,
    Review,
    UserSettings,
)
from app.db.session import (
    async_dsn,
    dispose_engine,
    get_db,
    get_engine,
    get_sessionmaker,
)

__all__ = [
    "Base",
    "Card",
    "FeatureFlag",
    "Language",
    "LlmBudget",
    "LlmUsage",
    "Profile",
    "Proficiency",
    "PromptVersion",
    "Review",
    "UserSettings",
    "async_dsn",
    "dispose_engine",
    "get_db",
    "get_engine",
    "get_sessionmaker",
]
