"""Declarative base for the SQLAlchemy ORM models.

Every ORM model inherits from :class:`Base`; ``Base.metadata`` is the single ``MetaData``
collection that Alembic targets (Phase 1.4) and the metadata tests introspect.

A Postgres-flavored naming convention is attached so generated index/constraint names are
deterministic (and close to what Postgres itself produces for the canonical Supabase migration),
which keeps Alembic autogenerate from churning on anonymous names. Multi-column constraints that
must carry an exact canonical name still set it explicitly on the model (see :mod:`app.db.models`).
"""

from __future__ import annotations

from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "%(table_name)s_%(column_0_name)s_key",
    "ck": "%(table_name)s_%(constraint_name)s_check",
    "fk": "%(table_name)s_%(column_0_name)s_fkey",
    "pk": "%(table_name)s_pkey",
}


class Base(DeclarativeBase):
    """Declarative base shared by every Lengua ORM model."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)
