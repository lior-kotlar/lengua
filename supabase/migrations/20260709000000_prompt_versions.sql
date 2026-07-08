-- Prompt versions: append-only, versioned LLM-prompt overrides, locked down to the server (GitHub #80)
--
-- public.prompt_versions moves the LLM prompt fragments out of the code and into the DB WITH history,
-- so an operator can tweak a prompt in prod — or roll back to an older wording — WITHOUT a code
-- change + redeploy. Each logical fragment (rules, generation_instruction, vocalization_instruction,
-- level_instruction, output_format, suggestion_instruction) is keyed by `key`; every edit APPENDS a
-- new row with the next `version` for that key, and the active pointer (`is_active`) moves. Generation
-- resolves the ACTIVE version by default (a caller may pin an explicit positive version); the app
-- caches the active set with a TTL (app.prompt_store) so a change is picked up within the TTL. The
-- in-code constants (lengua_core/prompts.py) remain the bootstrap seed (below) AND the runtime
-- fallback if the table is empty/unreachable — so the legacy Streamlit app + the CI/E2E FakeLLM path
-- keep working with zero DB dependency.
--
-- SECURITY — this is GLOBAL config, NOT user data. Exactly like feature_flags / llm_budget, the
-- prompts must be unreadable AND unwritable by the non-privileged `authenticated`/`anon` roles, or a
-- logged-in user could read or rewrite the prompts for everyone via PostgREST. So:
--   1. REVOKE ALL ON prompt_versions FROM authenticated, anon — no client SELECT/INSERT/UPDATE/DELETE.
--      The active prompt text reaches the model ONLY through the server's privileged app connection;
--      it is never exposed to clients. Writes (new versions / flipping is_active) are admin/
--      service-role only (SQL / a future admin endpoint — out of scope for #80).
--   2. ENABLE ROW LEVEL SECURITY with NO policy (deny-by-default) as a second lock, so a stray future
--      `GRANT ALL ... TO authenticated` can't silently re-expose it. The `postgres` owner (the
--      backend's app + migration role) and `service_role` both bypass RLS (no FORCE), so the server
--      read/write path is unchanged — mirrors feature_flags / llm_budget exactly.
--
-- Kept SEMANTICALLY in lockstep with Alembic migration 0007 — same table, indexes, seed rows, and
-- grants. (The Alembic file guards every role REVOKE with `to_regrole(...)` so it also round-trips on
-- a bare Postgres that lacks these Supabase roles; this canonical SQL runs them unconditionally
-- because it only ever runs on a real Supabase database.)

-- ── The append-only, versioned prompt-override table ───────────────────────────────────────────
create table if not exists public.prompt_versions (
  id         uuid        primary key default gen_random_uuid(),
  key        text        not null,   -- logical fragment key (rules, output_format, ...)
  version    int         not null,   -- monotonically increasing per key, starts at 1
  content    text        not null,   -- the template text (may contain {placeholders})
  is_active  boolean     not null default false,  -- at most one active version per key
  note       text,                   -- changelog note for this version
  created_at timestamptz not null default now(),
  created_by text,
  constraint prompt_versions_key_version_key unique (key, version)
);

-- At most one active version per key (roll back by moving this pointer, not by deleting newer rows).
create unique index if not exists prompt_versions_one_active_per_key
  on public.prompt_versions (key) where is_active;

-- ── Seed version 1 (active) for every key from the in-code defaults ────────────────────────────
-- Dollar-quoted so the prompt text (which contains apostrophes) needs no escaping. This is a
-- point-in-time snapshot of the code defaults; later edits are NEW versions, not migration changes.
insert into public.prompt_versions (key, version, content, is_active, note) values
  ('rules', 1, $prompt$Please strictly follow the rules and preferences below:

#### 1. Core Principle: Absolute Naturalness Over Everything
  - Prioritize how a native speaker would naturally choose to phrase things in casual, real-life conversations.
  - Never force words together into a sentence if it compromises the flow, logic, or cultural authenticity. If a sentence feels like a stiff, literal textbook translation, discard it.
  - Avoid literal translations of idioms. Choose simpler, punchier, or more idiomatic contexts that a native speaker would naturally prefer.

#### 2. High-Context & Definitive Scenarios
  - Ensure the context of the sentence actively reflects and illuminates the unique meaning, physical characteristics, behavior, or function of the vocabulary word.
  - Avoid generic, low-context sentences where the target word could easily be swapped for almost any other object or concept (e.g., for "dog", do NOT write "Look at the dog across the street," because "dog" could be replaced by "car", "tree", or "man").
  - DO create high-context scenarios that rely on characteristics unique to that word (e.g., "Don't worry, the dog might bark, but it won't bite," or "Please put your dog on a leash so it doesn't run into traffic"). The sentence must make it clear why that exact word is necessary.

#### 3. Word Packing & Complexity
  - Aim for a sweet spot of 2 to 3 vocabulary words per sentence by grouping them logically into realistic scenarios.
  - If words cannot be naturally paired without feeling forced, break them up into separate, simpler sentences.
  - You may repeat a vocabulary word across different sentences if it helps maintain an authentic context.
  - If the list provides both the singular and plural forms of a noun as separate entries, generate distinct contexts for each to demonstrate how their usage naturally shifts in conversation.

#### 4. Grammar & Pronunciation
  - Conjugate all verbs naturally to fit the specific scenario (even if they are provided in their root or infinitive forms in the word list).
  - Include any relevant pronunciation aids, accent marks, or phonetic guides within the sentence when they are critical for a learner reading the target language's script.

#### 5. Compulsory Quality Control (The Double-Review Rule)
  - Before finalizing, review each sentence internally at least twice.
  - If a sentence feels even slightly forced, awkward, or structurally stiff, replace it entirely with a more natural, context-rich phrase before presenting the final output.$prompt$, true, 'Seeded from the in-code default (migration).'),
  ('generation_instruction', 1, $prompt$You are helping a student learn {language}. Using the vocabulary words supplied by the user, write natural example sentences in {language} that follow all the rules above. Together, the sentences must use every one of the supplied vocabulary words at least once.$prompt$, true, 'Seeded from the in-code default (migration).'),
  ('vocalization_instruction', 1, $prompt$Write every word in the {language} sentence fully vocalized: include all vowel marks / diacritics (e.g., Arabic harakat, Hebrew niqqud) on every word, as in a fully-pointed beginner text. The English translation stays unchanged.$prompt$, true, 'Seeded from the in-code default (migration).'),
  ('level_instruction', 1, $prompt$Write the {language} sentences for a learner at CEFR level {level}. Match that level's typical sentence length, grammar, and vocabulary: at A1/A2 keep them short and simple with high-frequency words and basic tenses; at B1 use longer connected clauses and common idioms; at B2/C1/C2 allow long, multi-clause sentences with richer vocabulary, idioms, and varied tenses. The English translation stays natural.$prompt$, true, 'Seeded from the in-code default (migration).'),
  ('output_format', 1, $prompt$Output format — return a list of items, where each item has exactly these fields:
- "sentence": the example sentence in {language}, with correct spelling, accents, and any critical pronunciation aids.
- "translation": a natural English translation of the sentence (faithful, not word-for-word).
- "used_words": the list of supplied vocabulary words that appear in the sentence.
- "word_notes": a list of {{"word", "note"}} objects, one for each meaningful word in the sentence. "word" is the word exactly as it appears in the sentence (keep all vowel marks / diacritics). "note" is a brief gloss — at most two sentences covering its meaning and role in this sentence; for a very simple or common word (e.g. "to", "in", "and") a single word or short phrase is enough.
Do not add any other text, commentary, or numbering outside these fields.$prompt$, true, 'Seeded from the in-code default (migration).'),
  ('suggestion_instruction', 1, $prompt$You are a {language} vocabulary coach.

Pick exactly {count} vocabulary words in {language} that are appropriate for a CEFR {level_band} learner. Choose words that are useful, natural, and suited to that level's typical range — not too simple, not too advanced.{topic_line}

{known_block}

Return ONLY a JSON array of {count} strings, e.g. ["word1", "word2"]. No explanations, no numbering, no extra text.$prompt$, true, 'Seeded from the in-code default (migration).')
on conflict (key, version) do nothing;

-- ── Lock it down: server-only (no client reads/writes) + deny-by-default RLS ────────────────────
revoke all on table public.prompt_versions from authenticated, anon;
alter table public.prompt_versions enable row level security;  -- no policy → deny-all (owner bypasses)
