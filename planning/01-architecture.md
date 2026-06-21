# 01 — Architecture

## System overview

```
                          ┌───────────────────────────────────────────┐
                          │                 Clients                    │
                          │                                            │
        Web browser ──────┤  React + TS app (Vite build)               │
        iOS app ──────────┤   • same codebase, wrapped by Capacitor    │
        Android app ──────┤   • supabase-js for auth (login/signup)    │
                          │   • calls FastAPI with Bearer <JWT>        │
                          └───────────────┬───────────────────────────┘
                                          │ HTTPS (JSON)
                                          │ Authorization: Bearer <supabase access token>
                                          ▼
                          ┌───────────────────────────────────────────┐
                          │         FastAPI backend (Cloud Run)        │
                          │                                            │
                          │  • verifies Supabase JWT (per request)     │
                          │  • scopes every query by user_id           │
                          │  • ports lengua/ core:                     │
                          │      gemini / scheduler / proficiency /    │
                          │      flashcards / prompts                  │
                          │  • Gemini quota + rate-limit gate          │
                          │  • OpenTelemetry instrumented              │
                          └───┬───────────────┬───────────────┬───────┘
                              │               │               │
              SQLAlchemy      │       OTLP    │      HTTPS     │
                              ▼               ▼               ▼
                  ┌───────────────────┐  ┌──────────┐  ┌──────────────┐
                  │ Supabase Postgres │  │ Grafana  │  │  Gemini API  │
                  │  + Auth + RLS     │  │  Cloud   │  │ (Google AI)  │
                  └───────────────────┘  └──────────┘  └──────────────┘
                          │
                          └── Supabase Auth issues JWTs the client logs in with directly
```

## Component responsibilities

| Component | Responsibility |
| --- | --- |
| **React app** | All UI; auth via supabase-js; talks to FastAPI for everything else. One build → web (static host) + iOS/Android (Capacitor). |
| **FastAPI** | The only thing that talks to the LLM provider (Groq by default now / Gemini later; key stays server-side) and the only writer of domain data. Verifies JWTs, enforces ownership + quotas, runs FSRS/proficiency logic. |
| **Supabase Auth** | Sign-up/login, email verification, password reset, OAuth (Google/Apple), JWT issuance + refresh. |
| **Supabase Postgres** | System of record. RLS on every table as defense-in-depth. |
| **LLM provider (Groq / Gemini)** | Sentence/word generation + explanations, behind one provider interface picked by `LLM_PROVIDER` — **default Groq** (free tier; all dev now), flip to **Gemini** anytime (later / prod). Called only from FastAPI, behind the quota gate. |
| **Grafana Cloud / Sentry** | Telemetry + error tracking. |

## Why this shape

- **FastAPI in front of the LLM provider, not the client calling Supabase directly.** The
  provider key (Groq or Gemini) must never reach the client, and the domain logic (FSRS
  scheduling, proficiency math, dual card creation, prompt assembly) is already Python. So a
  server is required regardless; we centralize all writes there. The client uses Supabase
  *only* for auth.
- **Capacitor over React Native/Flutter.** The app is text-and-forms with complex script
  rendering (Arabic/Hebrew + diacritics, RTL). The web layer renders that beautifully and one
  React codebase serves all three platforms — lowest cost, max reuse.
- **One LLM provider seam, default Groq.** All generation goes through a single `llm` interface,
  so the model behind it is a config choice, not a code change. We build and test everything on
  **Groq's free tier** now; flipping `LLM_PROVIDER=gemini` (any env) later validates real prompt
  output and serves prod. Same call signatures, same Pydantic results, same quota gate — only
  the provider impl and key differ.

## Auth flow

1. Client signs in via `supabase-js` → receives `access_token` (JWT) + `refresh_token`.
2. Client stores tokens (web: Supabase's storage; mobile: Capacitor Preferences/secure
   storage) and sends `Authorization: Bearer <access_token>` on every API call.
3. FastAPI verifies the JWT (Supabase JWT secret / JWKS), extracts `sub` = user UUID.
4. FastAPI scopes all DB access to that UUID. RLS provides a second layer in the DB.
5. On 401, the client refreshes via supabase-js and retries.

## Generation flow (with cost guard)

```
client → POST /generate {words, language_id}
  → FastAPI: verify JWT → resolve user
  → quota gate:  per-user daily cap?  per-user rate limit?  global daily budget left?
       └─ if blocked → 429 with friendly reason (no Gemini call)
  → llm.generate_cards(words, level_band)   [active provider — Groq now / Gemini later, with retry/backoff]
  → lengua.flashcards.save_cards(...)  → 2 cards/sentence, tagged gen_level, persisted
  → record usage (user_id, day, kind) for caps + the global budget counter
  → 200 with created cards
```

## Multi-tenant data model (the redesign)

Today `languages.name` is globally `UNIQUE` and `settings` is a single global key/value
table. **Both break under multi-user and must be re-scoped.** Plan:

- **Identity:** use the Supabase `auth.users` UUID as the user id everywhere. Add an app-level
  `profiles` table (PK = that UUID) for app-specific fields, including a `plan` field (default
  `free`) so optional paid tiers are a later config change, not a migration. **`user_id`
  becomes a UUID**, not the integer `1` the current schema assumes.
- **Add `user_id` (UUID, FK → profiles) to:** `languages`, `cards`, `reviews`, `settings`,
  `proficiency` (already has one — change its type to UUID and make it a real FK).
- **Re-scope uniqueness:** `languages` → `UNIQUE(user_id, name)`; `settings` → PK
  `(user_id, key)` (these become *per-user preferences*: daily limits, discover count).
- **Operator-global config leaves the DB:** the LLM provider selection (`LLM_PROVIDER`), model
  name, and the operator API key move to environment/secrets (operator-funded — users don't
  pick the provider or key).
- **New tables:** `gemini_usage` (per-user/day counters for caps) and a `gemini_budget`
  day-counter (project-wide kill-switch). See DDL sketch in [03-backend.md](03-backend.md).
- **Type modernization for Postgres:** `timestamptz` for timestamps, `jsonb` for
  `fsrs_state` / `used_words` / `word_explanations`, identity/UUID PKs, real FKs with
  `ON DELETE CASCADE`.
- **Enable RLS** on all user tables: `user_id = auth.uid()`.

## Repository layout (monorepo)

```
lengua/                         # repo root
  apps/
    api/                        # FastAPI service
      lengua_core/              # the ported lengua/* package (gemini, scheduler, ...)
      app/                      # http layer: routers, deps, auth, quota, otel
      migrations/               # Alembic
      tests/
      Dockerfile
      pyproject.toml
    web/                        # React + TS (Vite)
      src/
      capacitor.config.ts       # Capacitor wrap config
      ios/  android/            # generated native projects
  packages/
    api-types/                  # OpenAPI-generated TS client/types (shared)
  infra/
    github-actions/             # CI/CD workflows (or .github/workflows)
    supabase/                   # supabase CLI config, SQL policies, seed
  planning/                     # these documents
  docs/                         # privacy policy, legal, runbooks
```

*(The current top-level `lengua/`, `pages/`, `app.py` are migrated into `apps/api` and
`apps/web`; the legacy Streamlit app can stay runnable during the transition or be retired
once the React app reaches parity.)*

## Environments

| Env | Frontend | Backend | DB + Auth | Purpose |
| --- | --- | --- | --- | --- |
| **local** | Vite dev server | uvicorn | Supabase CLI (Docker), free/unlimited | Day-to-day dev |
| **staging** | Vercel (preview/staging) | Cloud Run (staging) | Supabase free project #1 | Integration, QA, store test builds |
| **prod** | Vercel (production) | Cloud Run (prod) | Supabase free project #2 | Live users |

`local` uses the Supabase CLI stack so it doesn't consume a hosted project slot — keeping us
within the free-tier active-project limit. Details + free-tier limits table in
[05-infra-deploy.md](05-infra-deploy.md).
