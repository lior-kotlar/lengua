"""feature flags — global operator config table, locked down to the server (task 6.9.1)

Revision ID: 0005
Revises: 0004
Create Date: 2026-06-28

Adds ``public.feature_flags`` — the small GLOBAL table that overlays the env-driven feature flags
(:mod:`app.feature_flags`) so a risky/new feature can be toggled in prod WITHOUT a redeploy: a row
``(name, enabled, updated_at)`` overrides the env default for that flag for *everyone*, picked up by
the app within ``FEATURE_FLAG_TTL_SECONDS``. Absence of a row ⇒ fall back to the env default (off).

**Security — this is GLOBAL config, not user data (call out for review).** Exactly like
``llm_budget`` (the global kill-switch counter, migration 0004), ``feature_flags`` must be
unwritable — and here unreadable — by the non-privileged ``authenticated``/``anon`` roles, or a
logged-in user could flip a flag on for everyone via Supabase's PostgREST. So this migration:

1. ``REVOKE ALL ON feature_flags FROM authenticated, anon`` — no client SELECT/INSERT/UPDATE/DELETE.
   The flag state reaches the browser ONLY through the public ``GET /feature-flags`` API endpoint
   (which the server resolves on the privileged app connection), never by reading this table
   directly. Writes are admin/service-role only (toggled by the operator via a privileged session —
   see the runbook / ``app.feature_flags`` docstring).
2. ``ENABLE ROW LEVEL SECURITY`` with **no policy** (deny-by-default) — a second lock so a stray
   future ``GRANT ALL … TO authenticated`` can't silently re-expose it. The connecting
   ``postgres``/owner role (the backend's app + migration role) and ``service_role`` both bypass RLS
   (no ``FORCE``), so the server read/write path is unaffected — this mirrors ``llm_budget`` exactly.

**Bare-Postgres safety.** The table + ``ENABLE ROW LEVEL SECURITY`` reference only real objects, so
they apply on every database (the CI schema round-trip harness runs a bare Postgres). The
``authenticated``/``anon`` roles exist only on a Supabase database, so each ``REVOKE`` is guarded by
``to_regrole(...) IS NOT NULL`` inside a ``DO`` block — a clean no-op on bare Postgres. ``downgrade``
drops the table outright (its RLS + privileges go with it), keeping the round-trip reversible on both
kinds of database.

Kept SEMANTICALLY in lockstep with ``supabase/migrations/20260628000000_feature_flags.sql`` — same
table + grants; only the role-statement guarding differs (Alembic guards via ``to_regrole``; the
Supabase SQL runs unconditionally, as it only ever runs on a real Supabase DB).

⚠️ **Production caveat:** do NOT ``alembic downgrade`` past 0005 in production — it drops the global
feature-flag overrides (every prod flag reverts to its env default). (Carry this into the Phase 6
deploy runbook; see docs/runbook.md.)
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# Deny-by-default RLS on the global flag table (no policy). Unconditional — works on bare Postgres
# (no role needed); the owner/service-role bypass RLS so the server path is unaffected.
_ENABLE_RLS = "alter table feature_flags enable row level security"
_DISABLE_RLS = "alter table feature_flags disable row level security"

# Role grants/revokes only exist on a Supabase DB — guard so a bare Postgres still round-trips.
_LOCK_DOWN_ROLES = """
do $$
begin
  if to_regrole('authenticated') is not null then
    revoke all on table feature_flags from authenticated;
  end if;
  if to_regrole('anon') is not null then
    revoke all on table feature_flags from anon;
  end if;
end
$$;
"""


def upgrade() -> None:
    op.create_table(
        "feature_flags",
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("name", name="feature_flags_pkey"),
    )
    op.execute(_ENABLE_RLS)
    op.execute(_LOCK_DOWN_ROLES)


def downgrade() -> None:
    # Dropping the table removes its RLS + role privileges with it (no separate restore needed).
    op.execute(_DISABLE_RLS)
    op.drop_table("feature_flags")
