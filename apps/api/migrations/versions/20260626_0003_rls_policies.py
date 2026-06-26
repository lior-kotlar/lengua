"""row-level security — enable RLS + owner policies on every user table (task 2.6.1)

Revision ID: 0003
Revises: 0002
Create Date: 2026-06-26

Reproduces, in Alembic, the Row-Level-Security section the canonical Supabase migration
(``supabase/migrations/20260621000000_initial_schema.sql``) already defines: RLS is enabled on the
seven per-user tables and each gets an owner policy so a row is only visible/writable to the user
that owns it —

* ``profiles``      ``using (id = auth.uid())      with check (id = auth.uid())``
* ``languages`` / ``cards`` / ``reviews`` / ``proficiency`` / ``user_settings`` / ``llm_usage``
  ``using (user_id = auth.uid()) with check (user_id = auth.uid())``

``llm_budget`` is intentionally left global (no RLS — only the service role writes it). The policy
names and predicates are kept byte-for-byte consistent with the canonical SQL so the two schema
sources never drift, and so a database built by ``alembic upgrade head`` is indistinguishable (for
RLS purposes) from one built by ``supabase db reset``.

**Bare-Postgres safety.** The policy predicates reference ``auth.uid()``, a function that only
exists on a Supabase database (created by GoTrue's own migrations). The CI schema round-trip tests
run ``alembic upgrade head`` / ``downgrade base`` against a *bare* Postgres that has no ``auth``
schema, where ``CREATE POLICY … auth.uid()`` would fail at parse time. So the whole block is
guarded on ``to_regprocedure('auth.uid()')`` resolving: on a Supabase database every statement
runs; on a bare database the migration is a clean no-op (RLS stays a Supabase concern, exactly as
the Phase-1 ORM/migration treats the ``auth.users`` FK and the ``handle_new_user`` trigger). The
matching guard in ``downgrade`` keeps the round-trip reversible on both kinds of database.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# (table, owner-column) for the seven RLS-protected tables. ``profiles`` keys on its own PK ``id``
# (it *is* the user row); the rest key on ``user_id``. Order is irrelevant — policies are independent.
_RLS_TABLES: tuple[tuple[str, str], ...] = (
    ("profiles", "id"),
    ("languages", "user_id"),
    ("cards", "user_id"),
    ("reviews", "user_id"),
    ("proficiency", "user_id"),
    ("user_settings", "user_id"),
    ("llm_usage", "user_id"),
)


def _has_auth_uid() -> bool:
    """True when ``auth.uid()`` exists (i.e. this is a Supabase database, not a bare Postgres)."""
    bind = op.get_bind()
    return bool(bind.execute(sa.text("SELECT to_regprocedure('auth.uid()') IS NOT NULL")).scalar())


def upgrade() -> None:
    if not _has_auth_uid():
        return  # bare Postgres: RLS is a Supabase-only concern — nothing to do.
    for table, owner_col in _RLS_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        # Drop-then-create so the migration is idempotent across an upgrade→downgrade→upgrade cycle.
        op.execute(f"DROP POLICY IF EXISTS {table}_owner ON {table}")
        op.execute(
            f"CREATE POLICY {table}_owner ON {table} "
            f"USING ({owner_col} = auth.uid()) WITH CHECK ({owner_col} = auth.uid())"
        )


def downgrade() -> None:
    if not _has_auth_uid():
        return
    for table, _owner_col in _RLS_TABLES:
        op.execute(f"DROP POLICY IF EXISTS {table}_owner ON {table}")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
