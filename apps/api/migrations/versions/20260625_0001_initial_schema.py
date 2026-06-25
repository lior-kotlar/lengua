"""initial schema — full multi-tenant app schema (tasks 1.4.2 + 1.4.3)

Revision ID: 0001
Revises:
Create Date: 2026-06-25

The entire Lengua schema in one migration: the six app tables (``profiles``, ``languages``,
``cards`` + its ``(user_id, language_id, saved, due)`` lookup index, ``reviews``,
``proficiency``, ``user_settings``) plus the two cost-guard tables (``llm_usage`` PK
``(user_id, day, kind)`` and ``llm_budget`` PK ``day``), built now and used by the Phase 3
quota gate.

Mirrors the ORM models in ``app/db/models.py`` and the canonical
``supabase/migrations/20260621000000_initial_schema.sql`` — same UUID / timestamptz / jsonb /
real / ``bigint generated always as identity`` types, foreign keys (all ``ON DELETE CASCADE``),
per-user uniqueness, and primary keys.

Applyable on a **bare Postgres**: ``profiles.id`` is a plain ``uuid`` PK with no ``auth.users``
foreign key, and there are no RLS policies — those remain Supabase-migration / Phase-2 concerns.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "profiles",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("plan", sa.Text(), server_default=sa.text("'free'"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="profiles_pkey"),
    )

    op.create_table(
        "languages",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("code", sa.Text(), nullable=True),
        sa.Column("vowelized", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["profiles.id"], name="languages_user_id_fkey", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name="languages_pkey"),
        sa.UniqueConstraint("user_id", "name", name="languages_user_id_name_key"),
    )

    op.create_table(
        "cards",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("language_id", sa.BigInteger(), nullable=False),
        sa.Column("front", sa.Text(), nullable=False),
        sa.Column("back", sa.Text(), nullable=False),
        sa.Column("used_words", postgresql.JSONB(), nullable=True),
        sa.Column("direction", sa.Text(), nullable=True),
        sa.Column("word_explanations", postgresql.JSONB(), nullable=True),
        sa.Column("gen_level", sa.REAL(), nullable=True),
        sa.Column("saved", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("fsrs_state", postgresql.JSONB(), nullable=True),
        sa.Column("due", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["profiles.id"], name="cards_user_id_fkey", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["language_id"], ["languages.id"], name="cards_language_id_fkey", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name="cards_pkey"),
    )
    op.create_index(
        "cards_user_lang_due",
        "cards",
        ["user_id", "language_id", "saved", "due"],
        unique=False,
    )

    op.create_table(
        "reviews",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("card_id", sa.BigInteger(), nullable=False),
        sa.Column("rating", sa.SmallInteger(), nullable=False),
        sa.Column(
            "reviewed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["profiles.id"], name="reviews_user_id_fkey", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["card_id"], ["cards.id"], name="reviews_card_id_fkey", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name="reviews_pkey"),
    )

    op.create_table(
        "proficiency",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("language_id", sa.BigInteger(), nullable=False),
        sa.Column("score", sa.REAL(), server_default=sa.text("0.0"), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["profiles.id"], name="proficiency_user_id_fkey", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["language_id"],
            ["languages.id"],
            name="proficiency_language_id_fkey",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("user_id", "language_id", name="proficiency_pkey"),
    )

    op.create_table(
        "user_settings",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("key", sa.Text(), nullable=False),
        sa.Column("value", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"], ["profiles.id"], name="user_settings_user_id_fkey", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("user_id", "key", name="user_settings_pkey"),
    )

    op.create_table(
        "llm_usage",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"], ["profiles.id"], name="llm_usage_user_id_fkey", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("user_id", "day", "kind", name="llm_usage_pkey"),
    )

    op.create_table(
        "llm_budget",
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.PrimaryKeyConstraint("day", name="llm_budget_pkey"),
    )


def downgrade() -> None:
    # Drop in reverse dependency order (children before parents).
    op.drop_table("llm_budget")
    op.drop_table("llm_usage")
    op.drop_table("user_settings")
    op.drop_table("proficiency")
    op.drop_table("reviews")
    op.drop_index("cards_user_lang_due", table_name="cards")
    op.drop_table("cards")
    op.drop_table("languages")
    op.drop_table("profiles")
