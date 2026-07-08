"""prompt versions — append-only, versioned LLM-prompt overrides, locked down (GitHub #80)

Revision ID: 0007
Revises: 0006
Create Date: 2026-07-09

Adds ``public.prompt_versions`` — the append-only, versioned table that moves the LLM prompt
fragments out of the code and into the DB WITH history, so an operator can tweak a prompt in prod —
or roll back to an older wording — WITHOUT a code change + redeploy (GitHub #80). Each logical
fragment (``rules``, ``generation_instruction``, ``vocalization_instruction``, ``level_instruction``,
``output_format``, ``suggestion_instruction``) is keyed by ``key``; every edit APPENDS a new row with
the next ``version`` for that key and the active pointer (``is_active``) moves. Generation resolves
the ACTIVE version by default (:mod:`app.prompt_store`), caching it with a TTL so a change is picked
up without a redeploy. The in-code constants (:mod:`lengua_core.prompts`) remain the bootstrap seed
(inserted here as version 1) AND the runtime fallback when the table is empty/unreachable, so the
legacy Streamlit app + the CI/E2E FakeLLM path keep working with zero DB dependency.

**Security — this is GLOBAL config, not user data (call out for review).** Exactly like
``feature_flags`` / ``llm_budget``, ``prompt_versions`` must be unreadable AND unwritable by the
non-privileged ``authenticated``/``anon`` roles, or a logged-in user could read or rewrite the
prompts for everyone via Supabase's PostgREST. So this migration:

1. ``REVOKE ALL ON prompt_versions FROM authenticated, anon`` — no client
   SELECT/INSERT/UPDATE/DELETE. The active prompt text reaches the model only through the server's
   privileged app connection; it is never exposed to clients. Writes (new versions / flipping the
   active pointer) are admin/service-role only.
2. ``ENABLE ROW LEVEL SECURITY`` with **no policy** (deny-by-default) — a second lock so a stray
   future ``GRANT ALL … TO authenticated`` can't silently re-expose it. The connecting
   ``postgres``/owner role (the backend's app + migration role) and ``service_role`` both bypass RLS
   (no ``FORCE``), so the server read/write path is unaffected — this mirrors ``feature_flags``
   exactly.

**Bare-Postgres safety.** The table, indexes, seed INSERTs, and ``ENABLE ROW LEVEL SECURITY``
reference only real objects, so they apply on every database (the CI schema round-trip harness runs a
bare Postgres). The ``authenticated``/``anon`` roles exist only on a Supabase database, so each
``REVOKE`` is guarded by ``to_regrole(...) IS NOT NULL`` inside a ``DO`` block — a clean no-op on bare
Postgres. ``downgrade`` drops the table outright (its indexes, RLS, privileges, and seed rows go with
it), keeping the round-trip reversible on both kinds of database.

Kept SEMANTICALLY in lockstep with ``supabase/migrations/20260709000000_prompt_versions.sql`` — same
table, indexes, seed rows, and grants; only the role-statement guarding differs (Alembic guards via
``to_regrole``; the Supabase SQL runs unconditionally, as it only ever runs on a real Supabase DB).

The seed rows embed the exact in-code default text as version 1 (active). This is a point-in-time
snapshot; ``tests/test_prompt_store.py`` asserts the seeded content matches
:data:`lengua_core.prompts.CODE_DEFAULTS`. Later prompt edits are NEW versions in the table, not edits
to this migration.

⚠️ **Production caveat:** do NOT ``alembic downgrade`` past 0007 in production — it drops every
prompt version (including any active overrides authored in prod); generation then falls back to the
in-code defaults. (Carry this into the deploy runbook; see docs/runbook.md.)
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# Deny-by-default RLS on the global prompt table (no policy). Unconditional — works on bare Postgres
# (no role needed); the owner/service-role bypass RLS so the server path is unaffected.
_ENABLE_RLS = "alter table prompt_versions enable row level security"
_DISABLE_RLS = "alter table prompt_versions disable row level security"

# Partial unique index: at most one active version per key (DB-level guarantee).
_ACTIVE_INDEX = (
    "create unique index prompt_versions_one_active_per_key "
    "on prompt_versions (key) where is_active"
)

# Seed rows: one per key, version 1, active, content = the in-code default. Dollar-quoted so the
# prompt text (which contains apostrophes) needs no escaping. One statement per op.execute (asyncpg's
# extended-query protocol forbids multi-command strings).
_SEED_ROWS: tuple[tuple[str, str], ...] = (
    ('rules', 'Please strictly follow the rules and preferences below:\n\n#### 1. Core Principle: Absolute Naturalness Over Everything\n  - Prioritize how a native speaker would naturally choose to phrase things in casual, real-life conversations.\n  - Never force words together into a sentence if it compromises the flow, logic, or cultural authenticity. If a sentence feels like a stiff, literal textbook translation, discard it.\n  - Avoid literal translations of idioms. Choose simpler, punchier, or more idiomatic contexts that a native speaker would naturally prefer.\n\n#### 2. High-Context & Definitive Scenarios\n  - Ensure the context of the sentence actively reflects and illuminates the unique meaning, physical characteristics, behavior, or function of the vocabulary word.\n  - Avoid generic, low-context sentences where the target word could easily be swapped for almost any other object or concept (e.g., for "dog", do NOT write "Look at the dog across the street," because "dog" could be replaced by "car", "tree", or "man").\n  - DO create high-context scenarios that rely on characteristics unique to that word (e.g., "Don\'t worry, the dog might bark, but it won\'t bite," or "Please put your dog on a leash so it doesn\'t run into traffic"). The sentence must make it clear why that exact word is necessary.\n\n#### 3. Word Packing & Complexity\n  - Aim for a sweet spot of 2 to 3 vocabulary words per sentence by grouping them logically into realistic scenarios.\n  - If words cannot be naturally paired without feeling forced, break them up into separate, simpler sentences.\n  - You may repeat a vocabulary word across different sentences if it helps maintain an authentic context.\n  - If the list provides both the singular and plural forms of a noun as separate entries, generate distinct contexts for each to demonstrate how their usage naturally shifts in conversation.\n\n#### 4. Grammar & Pronunciation\n  - Conjugate all verbs naturally to fit the specific scenario (even if they are provided in their root or infinitive forms in the word list).\n  - Include any relevant pronunciation aids, accent marks, or phonetic guides within the sentence when they are critical for a learner reading the target language\'s script.\n\n#### 5. Compulsory Quality Control (The Double-Review Rule)\n  - Before finalizing, review each sentence internally at least twice.\n  - If a sentence feels even slightly forced, awkward, or structurally stiff, replace it entirely with a more natural, context-rich phrase before presenting the final output.'),
    ('generation_instruction', 'You are helping a student learn {language}. Using the vocabulary words supplied by the user, write natural example sentences in {language} that follow all the rules above. Together, the sentences must use every one of the supplied vocabulary words at least once.'),
    ('vocalization_instruction', 'Write every word in the {language} sentence fully vocalized: include all vowel marks / diacritics (e.g., Arabic harakat, Hebrew niqqud) on every word, as in a fully-pointed beginner text. The English translation stays unchanged.'),
    ('level_instruction', "Write the {language} sentences for a learner at CEFR level {level}. Match that level's typical sentence length, grammar, and vocabulary: at A1/A2 keep them short and simple with high-frequency words and basic tenses; at B1 use longer connected clauses and common idioms; at B2/C1/C2 allow long, multi-clause sentences with richer vocabulary, idioms, and varied tenses. The English translation stays natural."),
    ('output_format', 'Output format — return a list of items, where each item has exactly these fields:\n- "sentence": the example sentence in {language}, with correct spelling, accents, and any critical pronunciation aids.\n- "translation": a natural English translation of the sentence (faithful, not word-for-word).\n- "used_words": the list of supplied vocabulary words that appear in the sentence.\n- "word_notes": a list of {{"word", "note"}} objects, one for each meaningful word in the sentence. "word" is the word exactly as it appears in the sentence (keep all vowel marks / diacritics). "note" is a brief gloss — at most two sentences covering its meaning and role in this sentence; for a very simple or common word (e.g. "to", "in", "and") a single word or short phrase is enough.\nDo not add any other text, commentary, or numbering outside these fields.'),
    ('suggestion_instruction', 'You are a {language} vocabulary coach.\n\nPick exactly {count} vocabulary words in {language} that are appropriate for a CEFR {level_band} learner. Choose words that are useful, natural, and suited to that level\'s typical range — not too simple, not too advanced.{topic_line}\n\n{known_block}\n\nReturn ONLY a JSON array of {count} strings, e.g. ["word1", "word2"]. No explanations, no numbering, no extra text.'),
)

# Role grants/revokes only exist on a Supabase DB — guard so a bare Postgres still round-trips.
_LOCK_DOWN_ROLES = """
do $$
begin
  if to_regrole('authenticated') is not null then
    revoke all on table prompt_versions from authenticated;
  end if;
  if to_regrole('anon') is not null then
    revoke all on table prompt_versions from anon;
  end if;
end
$$;
"""


def upgrade() -> None:
    op.create_table(
        "prompt_versions",
        sa.Column(
            "id",
            sa.Uuid(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("key", sa.Text(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("created_by", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id", name="prompt_versions_pkey"),
        sa.UniqueConstraint("key", "version", name="prompt_versions_key_version_key"),
    )
    op.execute(_ACTIVE_INDEX)
    # Seed each key's version-1 (active) row from the in-code default, bound as a parameter so the
    # multi-line content is passed verbatim (no SQL-literal escaping in the migration body).
    insert = sa.text(
        "insert into prompt_versions (key, version, content, is_active, note) "
        "values (:key, 1, :content, true, "
        "'Seeded from the in-code default (migration).') "
        "on conflict (key, version) do nothing"
    )
    for key, content in _SEED_ROWS:
        op.execute(insert.bindparams(key=key, content=content))
    op.execute(_ENABLE_RLS)
    op.execute(_LOCK_DOWN_ROLES)


def downgrade() -> None:
    # Dropping the table removes its indexes, RLS, role privileges, and seed rows with it.
    op.execute(_DISABLE_RLS)
    op.drop_table("prompt_versions")
