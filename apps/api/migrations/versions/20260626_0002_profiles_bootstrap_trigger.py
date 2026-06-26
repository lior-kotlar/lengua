"""profiles-on-first-login trigger — handle_new_user() + on_auth_user_created (task 2.5.1)

Revision ID: 0002
Revises: 0001
Create Date: 2026-06-26

Reproduces, in Alembic, the profile-bootstrap mechanism the canonical Supabase migration
(``supabase/migrations/20260621000000_initial_schema.sql``) already defines: a
``security definer`` function ``public.handle_new_user()`` and an ``after insert`` trigger
``on_auth_user_created`` on ``auth.users`` that inserts a matching ``profiles`` row (``plan``
defaults to ``'free'``) for every newly-signed-up user. This is the canonical "a profiles row
exists for every user on first login" mechanism (no app-side write needed in the request path).

The function/trigger body is kept byte-for-byte consistent with the canonical SQL so the two
schema sources never drift.

**Bare-Postgres safety.** The CI round-trip tests (and any Cloud-SQL-without-GoTrue deploy) run
``alembic upgrade head`` against a database that has *no* ``auth`` schema. ``auth.users`` therefore
may not exist, so the trigger creation is guarded by a ``to_regclass('auth.users')`` check inside a
``DO`` block: the function is always created, and the trigger is created only where ``auth.users``
is present (a Supabase database). The matching guard in ``downgrade`` keeps the round-trip
reversible on both kinds of database.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# Matches supabase/migrations/20260621000000_initial_schema.sql verbatim (keep them in lockstep).
_CREATE_FUNCTION = """
create or replace function public.handle_new_user()
returns trigger
language plpgsql
security definer set search_path = public
as $$
begin
  insert into public.profiles (id) values (new.id);
  return new;
end;
$$;
"""

# auth.users only exists on a Supabase database; guard so a bare Alembic Postgres still upgrades.
_CREATE_TRIGGER_IF_AUTH = """
do $$
begin
  if to_regclass('auth.users') is not null then
    create or replace trigger on_auth_user_created
      after insert on auth.users
      for each row execute procedure public.handle_new_user();
  end if;
end
$$;
"""

_DROP_TRIGGER_IF_AUTH = """
do $$
begin
  if to_regclass('auth.users') is not null then
    drop trigger if exists on_auth_user_created on auth.users;
  end if;
end
$$;
"""


def upgrade() -> None:
    op.execute(_CREATE_FUNCTION)
    op.execute(_CREATE_TRIGGER_IF_AUTH)


def downgrade() -> None:
    op.execute(_DROP_TRIGGER_IF_AUTH)
    op.execute("drop function if exists public.handle_new_user();")
