# 03 — Backend (FastAPI)

> **Status: IMPLEMENTED (2026-07-05).** Realized in `apps/api/` + the root [`README.md`](../README.md) + [`docs/runbook.md`](../docs/runbook.md); Alembic `0001–0006` are the schema of record. Design rationale preserved in [`../CHANGELOG.md`](../CHANGELOG.md). Retained as historical design.

## Stack

- **FastAPI** + **uvicorn** (ASGI), containerized for Cloud Run.
- **SQLAlchemy 2.x** (or SQLModel) + **Alembic** migrations; **asyncpg** driver to Supabase
  Postgres.
- **Pydantic v2** for request/response models (already used in `lengua/models.py`).
- **PyJWT** for Supabase JWT verification.
- **OpenTelemetry** SDK + FastAPI/SQLAlchemy/httpx instrumentation.
- **LLM provider** behind a small `llm` interface, selected by `LLM_PROVIDER` (**default
  `groq`** — all development runs on Groq's free tier now; set `gemini` in any env to validate
  real prompts / serve prod, no code change). Impls: **Groq** (OpenAI-compatible API, free tier)
  and **Gemini** (`google-genai`, the existing `lengua/gemini.py`). Both implement
  `generate_cards` / `suggest_new_words` / `explain_word`, return the same Pydantic models, and
  run behind the same quota gate. Only the Gemini SDK gives native schema-parsed output; other
  providers use JSON mode and parse into `GeneratedCard` / `WordNote` themselves.

## Layering

```
app/
  main.py            # FastAPI app, OTel + middleware wiring
  deps.py            # get_db, current_user (JWT), quota gate
  auth.py            # Supabase JWT verification
  quota.py           # per-user caps, rate limit, global budget guard
  routers/           # languages, generate, cards, review, discover, explain,
                     # proficiency, settings, account, health
  schemas/           # Pydantic request/response DTOs
  services/          # orchestrates lengua_core + repositories
  repositories/      # all SQL; the only place that touches the DB
lengua_core/         # ported domain logic
  llm/               # provider interface + groq.py (default) / gemini.py (later), picked by LLM_PROVIDER
  ...                # scheduler, proficiency, prompts, models
migrations/          # Alembic
```

**Boundary rule:** routers → services → repositories → DB. `lengua_core` stays pure (no FastAPI,
no SQL) so it remains unit-testable and portable.

## Porting map (today → backend)

| Today | Becomes |
| --- | --- |
| `lengua/gemini.py` | `lengua_core/llm/` — a provider interface with `groq.py` (default, dev) and `gemini.py` (later/prod, unchanged logic) behind it; provider, key, and model from env (operator-funded), chosen by `LLM_PROVIDER`. Wrap calls so the quota gate runs first; non-Gemini providers parse JSON into the same `GeneratedCard` / `WordNote` models. |
| `lengua/scheduler.py` | `lengua_core/scheduler.py` — pure FSRS; reads limits from per-user settings passed in. |
| `lengua/proficiency.py` | `lengua_core/proficiency.py` — pure; `register_review` called by the review service. |
| `lengua/flashcards.py` | split: pure card-building stays in core; persistence moves to `repositories/cards.py`. |
| `lengua/prompts.py`, `models.py` | move as-is into `lengua_core/`. |
| `lengua/languages.py` | becomes per-user; logic in `services/languages.py` + repository. |
| `lengua/settings.py` | per-user settings service; **operator/global values (LLM provider + key + model) leave the DB for env**. |
| `lengua/db.py` (SQLite) | replaced by SQLAlchemy engine/session + repositories; Alembic owns schema. |
| `lengua/config.py` | becomes typed settings (`pydantic-settings`) reading env per environment. |

### Switching the LLM provider

The whole point of the `llm` seam: changing model providers is a **config flip, never a code
change**.

- `LLM_PROVIDER=groq` (default) → uses `GROQ_API_KEY` + `GROQ_MODEL`. This is what every dev,
  test, and CI run uses for now.
- `LLM_PROVIDER=gemini` → uses `GEMINI_API_KEY` + `GEMINI_MODEL`. Flip this **later** to
  eyeball real prompt quality on Gemini, or as the prod default at launch.

`llm.get_provider()` reads `LLM_PROVIDER` once at startup and returns the matching impl; routers
and services depend only on the interface. A provider mismatch (missing key for the selected
provider) fails fast at boot. Keep both keys configurable so the flip is instant; **for now only
the Groq key needs to be set.**

## Postgres schema (DDL sketch)

> Illustrative, not final. Key changes from SQLite: **UUID user ids**, `timestamptz`, `jsonb`,
> per-user uniqueness, real FKs, RLS. Identity = Supabase `auth.users(id)`.

```sql
-- App-specific user fields; PK mirrors Supabase auth.users.id
create table profiles (
  id           uuid primary key references auth.users(id) on delete cascade,
  plan         text not null default 'free',     -- monetization-ready; no billing in v1
  created_at   timestamptz not null default now()
);

create table languages (
  id           bigint generated always as identity primary key,
  user_id      uuid not null references profiles(id) on delete cascade,
  name         text not null,
  code         text,
  vowelized    boolean not null default false,
  created_at   timestamptz not null default now(),
  unique (user_id, name)                      -- was global UNIQUE(name)
);

create table cards (
  id                bigint generated always as identity primary key,
  user_id           uuid not null references profiles(id) on delete cascade,
  language_id       bigint not null references languages(id) on delete cascade,
  front             text not null,
  back              text not null,
  used_words        jsonb,
  direction         text,                     -- 'recognition' | 'production'
  word_explanations jsonb,
  gen_level         real,
  saved             boolean not null default false,
  fsrs_state        jsonb,                    -- fsrs.Card.to_dict()
  due               timestamptz,
  created_at        timestamptz not null default now()
);
create index on cards (user_id, language_id, saved, due);

create table reviews (
  id          bigint generated always as identity primary key,
  user_id     uuid not null references profiles(id) on delete cascade,  -- denormalized for scoping/RLS
  card_id     bigint not null references cards(id) on delete cascade,
  rating      smallint not null,              -- 1..4
  reviewed_at timestamptz not null default now()
);

create table proficiency (
  user_id     uuid not null references profiles(id) on delete cascade,
  language_id bigint not null references languages(id) on delete cascade,
  score       real not null default 0.0,
  updated_at  timestamptz not null default now(),
  primary key (user_id, language_id)
);

-- per-user preferences (daily limits, discover count). Was a global key/value table.
create table user_settings (
  user_id uuid not null references profiles(id) on delete cascade,
  key     text not null,
  value   text,
  primary key (user_id, key)
);

-- Gemini cost control
create table gemini_usage (
  user_id uuid not null references profiles(id) on delete cascade,
  day     date not null,
  kind    text not null,                      -- 'generate' | 'discover' | 'explain'
  count   int  not null default 0,
  primary key (user_id, day, kind)
);

create table gemini_budget (
  day   date primary key,
  count int not null default 0                -- project-wide calls today (kill-switch)
);
```

Then **enable RLS** on every user table, e.g.:
```sql
alter table cards enable row level security;
create policy cards_owner on cards using (user_id = auth.uid()) with check (user_id = auth.uid());
```

## API surface (first cut)

| Method + path | Purpose |
| --- | --- |
| `GET /health` | Liveness/readiness (no auth). |
| `GET /me` | Current profile + per-language levels. |
| `GET/POST/DELETE /languages` | List/add/remove the user's languages; toggle vowelized. |
| `POST /generate` | words + language → created cards (quota-gated). |
| `POST /discover` | auto-pick new words (optional topic/count) → preview, then accept. |
| `GET /review/due` | today's due batch (new vs due split). |
| `POST /review/{card_id}/grade` | submit Again/Hard/Good/Easy → FSRS reschedule + proficiency nudge. |
| `POST /cards/save` | persist generated cards into the deck (recognition + production). |
| `POST /explain` | tap-a-word explanation (quota-gated; cached). |
| `GET/PUT /proficiency/{language_id}` | read level; manual override. |
| `GET/PUT /settings` | per-user daily limits, discover count. |
| `GET /account/export`, `DELETE /account` | data export + account deletion (compliance). |

All except `/health` require a valid Supabase JWT; all reads/writes are scoped to the token's user.

## LLM quota subsystem (the cost guard)

This gate fronts **whichever provider is active** (Groq now, Gemini when you switch) — the
`gemini_usage` / `gemini_budget` table names are historical; ceilings are read from the active
provider's free-tier limits. Order of checks in `quota.py` before any LLM call:

1. **Email verified?** else 403.
2. **Per-user rate limit** (sliding window, e.g. N/min) → 429 if exceeded.
3. **Per-user daily cap** for the `kind` (from `user_settings`, bounded by a server max) via
   `gemini_usage` → 429 if exceeded.
4. **Global daily budget** via `gemini_budget` vs a configured ceiling safely below Gemini's
   free daily limit → 503/429 "daily limit reached" if exceeded.
5. On success, increment `gemini_usage` + `gemini_budget` atomically (same transaction).

Plus: concurrency cap, exponential backoff on Gemini 429/5xx (keep existing retry), cap
words-per-request and max output tokens, and reuse cached `word_explanations`. Every call
emits a span with model, latency, token counts, and which gate (if any) blocked it.

Caps are per-user today; because `profiles.plan` exists, they can become **plan-aware** later
(higher caps for a paid tier, or BYOK) without a schema change. Keep key resolution pluggable
so a user-supplied key can override the operator key — the growth escape hatch (see
[08-open-questions-and-costs.md](08-open-questions-and-costs.md)).

> ⚠️ Verify the **active provider's** *current* free-tier RPM/RPD/TPM for the chosen model and
> set the global ceiling from real numbers — they change. (Groq now: ~30 RPM / ~1K RPD per
> model, no card required; Gemini: verify when you switch.) The global guard is the backstop
> that honors "I don't want to pay."

## Config & secrets (per environment)

`pydantic-settings` reading env vars:
`LLM_PROVIDER` (default `groq`; `gemini` later), `GROQ_API_KEY`, `GROQ_MODEL`,
`GEMINI_API_KEY`, `GEMINI_MODEL`, `DATABASE_URL` (Supabase Postgres), `SUPABASE_JWT_SECRET`/
`SUPABASE_JWKS_URL`, `OTEL_EXPORTER_OTLP_ENDPOINT`/headers, `SENTRY_DSN`, `ENV`
(local/staging/prod), quota ceilings. Never commit secrets; sourced from Cloud Run secrets /
GitHub Actions secrets — see [05-infra-deploy.md](05-infra-deploy.md).

## Testing

- **Pure logic** (scheduler, proficiency, prompt assembly): fast unit tests, no DB/network.
- **Repositories/services**: integration tests against local Supabase / testcontainers Postgres.
- **Auth + RLS**: tests proving cross-user isolation.
- **Quota**: tests for each gate + the global kill-switch.
- **Contract**: assert the OpenAPI schema is stable so the generated TS client stays in sync.
