"""profiles.id → auth.users(id) FK ON DELETE CASCADE — close the S1 erasure gap

Revision ID: 0006
Revises: 0005
Create Date: 2026-06-30

**Why this exists (the Alembic-vs-canonical drift that caused S1).** The canonical Supabase
schema (``supabase/migrations/20260621000000_initial_schema.sql``) declares ``profiles.id`` as
``uuid primary key references auth.users(id) on delete cascade``. The Alembic chain that actually
builds **staging/prod** never reproduced that FK: revision ``0001`` deliberately created
``profiles.id`` as a *bare* uuid PK (so the migrations apply on a bare Postgres with no ``auth``
schema — see its module docstring), and the auth FK / RLS / ``handle_new_user`` trigger were left
as Supabase-only concerns added back piecemeal (``0002``/``0003``) — *except this FK, which was
never re-added*. Deploys run ``alembic upgrade head``, so staging/prod ended up with **no**
``profiles → auth.users`` FK. ``AccountDeletionService`` deletes only the ``auth.users`` row (via
the GoTrue Admin API) and relied on a cascade that therefore never fired — orphaning the
``profiles`` row and every domain row (languages/cards/reviews/proficiency/user_settings/
llm_usage) while ``DELETE /account`` still returned ``204``. That is a right-to-erasure failure
(finding **S1** in ``planning/staging-validation.md``).

This revision reconciles the two schema sources by adding the missing FK to the Alembic chain so a
DB built by ``alembic upgrade head`` matches one built by the canonical Supabase SQL. The
domain-table FKs (``… → profiles(id) ON DELETE CASCADE``) already exist from ``0001``, so once this
parent FK is present, deleting the ``auth.users`` row cascades the whole graph away. (Group 2.8's
``app/services/account.py`` also now deletes the ``profiles`` row explicitly as defense-in-depth,
so erasure holds even on a DB that has not yet had this migration applied.)

**Bare-Postgres safety / idempotency (mirrors 0002/0003).** ``auth.users`` only exists on a
Supabase database; the CI schema round-trip + ``alembic check`` run against a *bare* throwaway
Postgres with no ``auth`` schema. So the whole body is guarded on ``to_regclass('auth.users')``
resolving — on a bare DB this migration is a clean no-op (``profiles`` keeps the bare PK the ORM
``Base.metadata`` models, so the drift check stays green). It is also idempotent: if a
``profiles → auth.users`` FK already exists (the canonical Supabase DB used by local/CI already
has ``profiles_id_fkey`` from the SQL above) we no-op rather than erroring.

**Safe on existing data — why NOT VALID + VALIDATE, not a direct validated ADD.** A plain
``ALTER TABLE profiles ADD CONSTRAINT … FOREIGN KEY … REFERENCES auth.users`` validates every
existing row *while holding a lock that blocks concurrent writes to the busy, GoTrue-managed
``auth.users`` table* for the whole scan — i.e. it can stall logins/signups. The two-step form
(``ADD … NOT VALID`` skips the existing-row scan under a brief lock; ``VALIDATE CONSTRAINT`` then
scans under a weaker ``SHARE UPDATE EXCLUSIVE`` lock that does **not** block ``auth.users``
writes) is the standard low-risk way to add an FK to a populated, live table, and lets an operator
run the ``VALIDATE`` out-of-band if they prefer. ``profiles`` is small (one row per user) so the
practical cost here is negligible, but this is the correct, safe default. Crucially, the
constraint is *active and its ``ON DELETE CASCADE`` referential action fires even while still
``NOT VALID``* — so erasure is armed immediately, independent of the ``VALIDATE`` step.

**Pre-existing orphans.** If ``DELETE /account`` already ran on this DB while the FK was missing,
there may be orphaned ``profiles`` rows whose ``auth.users`` parent is gone — the exact S1
casualties. Those would make ``VALIDATE`` fail, so we erase them first: deleting an orphaned
``profiles`` row cascades its domain rows away (``0001``), *completing the erasure the broken
delete left half-done*. This only touches profiles with **no** matching ``auth.users`` row, which
on a Supabase DB can only arise from that bug (every legitimate profile is created by the
``handle_new_user`` trigger from an ``auth.users`` insert), so it is a safe, correct remediation —
not data loss. It is, however, irreversible (you cannot un-erase data), which ``downgrade`` notes.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Name the constraint exactly as Postgres auto-names the canonical inline reference
# (``references auth.users(id)`` on column ``id`` → ``<table>_<column>_fkey``), so the canonical
# Supabase DB's existing constraint and the one we add here are one and the same — making the
# idempotency guard and the downgrade drop line up across both schema sources.
_FK_NAME = "profiles_id_fkey"

# Erase the S1 orphans (profiles whose auth.users parent is already gone) so VALIDATE can pass; the
# 0001 ``… → profiles`` cascade removes their domain rows too. See the module docstring.
_DELETE_ORPHANS = """
DELETE FROM public.profiles p
 WHERE NOT EXISTS (SELECT 1 FROM auth.users u WHERE u.id = p.id)
"""

_ADD_FK_NOT_VALID = f"""
ALTER TABLE public.profiles
  ADD CONSTRAINT {_FK_NAME}
  FOREIGN KEY (id) REFERENCES auth.users (id) ON DELETE CASCADE
  NOT VALID
"""

_VALIDATE_FK = f"ALTER TABLE public.profiles VALIDATE CONSTRAINT {_FK_NAME}"


def _has_auth_users() -> bool:
    """True when ``auth.users`` exists (a Supabase database, not a bare Alembic Postgres)."""
    bind = op.get_bind()
    return bool(bind.execute(sa.text("SELECT to_regclass('auth.users') IS NOT NULL")).scalar())


def _profiles_auth_fk_exists() -> bool:
    """True when a FK from ``public.profiles`` to ``auth.users`` already exists (any name).

    Checked semantically against ``pg_constraint`` (not just by name) so we recognise the
    canonical Supabase-built constraint and stay a no-op there — the idempotency guard.
    """
    bind = op.get_bind()
    found = bind.execute(
        sa.text(
            "SELECT 1 FROM pg_constraint c "
            "JOIN pg_class t ON t.oid = c.conrelid "
            "JOIN pg_namespace tn ON tn.oid = t.relnamespace "
            "JOIN pg_class r ON r.oid = c.confrelid "
            "JOIN pg_namespace rn ON rn.oid = r.relnamespace "
            "WHERE c.contype = 'f' "
            "  AND tn.nspname = 'public' AND t.relname = 'profiles' "
            "  AND rn.nspname = 'auth'   AND r.relname = 'users' "
            "LIMIT 1"
        )
    ).scalar()
    return found is not None


def upgrade() -> None:
    if not _has_auth_users():
        return  # bare Postgres: the auth.users FK is a Supabase-only concern — nothing to do.
    if _profiles_auth_fk_exists():
        return  # idempotent: the canonical Supabase schema already declares this FK.
    op.execute(_DELETE_ORPHANS)  # remove S1 orphans so VALIDATE cannot fail on stale rows
    op.execute(_ADD_FK_NOT_VALID)  # brief lock, no existing-row scan; cascade is armed immediately
    op.execute(_VALIDATE_FK)  # weaker lock; does not block concurrent auth.users writes


def downgrade() -> None:
    # Guarded + idempotent, mirroring upgrade. On a bare Postgres this is a no-op. On a Supabase DB
    # it drops the FK (reverting to the pre-0006 state) — note that on a *canonical* Supabase DB
    # this also removes the FK the SQL migration declared, since they are the same constraint. The
    # orphan erasure in upgrade() is intentionally NOT reversed: deleted data cannot be restored.
    if not _has_auth_users():
        return
    if not _profiles_auth_fk_exists():
        return
    op.execute(f"ALTER TABLE public.profiles DROP CONSTRAINT IF EXISTS {_FK_NAME}")
