# Backend API contract — the learning-loop endpoints (staging validation research)

Maps the FastAPI endpoints (`apps/api`) the learning loop depends on, the cost-guard / rate-limit /
validation a test must respect, and how `apps/web` calls each one. This is the contract a staging
validation must exercise and the likely source of failures.

Source of truth: `apps/api/app/main.py` (router wiring), `apps/api/app/routers/*`,
`apps/api/app/schemas/*`, `apps/api/app/quota.py`, `apps/api/app/ratelimit.py`,
`apps/api/app/llm_runner.py`, `apps/api/app/auth.py`, `apps/api/app/deps.py`, and the committed
`apps/api/openapi.json`. Web client: `apps/web/src/lib/*`.

---

## Cross-cutting contract (applies to every authed endpoint)

### Auth (Supabase JWT — never a client-supplied id)
- **There is NO auth endpoint in FastAPI.** Sign-up / log-in / OAuth / password reset / sign-out all
  go through `supabase-js` directly from the browser (`apps/web/src/lib/auth.ts` →
  `getSupabaseClient().auth.*`). The backend only **verifies** the token.
- Every domain route depends on `current_user` / `get_current_user` (`app/deps.py`), which verifies
  the `Authorization: Bearer <supabase access token>` JWT (`app/auth.py:decode_supabase_jwt`):
  checks signature + `exp` + `aud` (`authenticated`), pulls the user UUID from `sub`. Missing /
  malformed / invalid / expired / wrong-aud / `alg:none` → **401** `{"detail": "..."}` with
  `WWW-Authenticate: Bearer` (never 403). HS256 shared-secret by default; RS256/ES256 JWKS when
  `SUPABASE_JWKS_URL` is set.
- `email_verified` is carried on `CurrentUser` and gates LLM spend (see cost guard). A staging test
  user must have a verified email to exercise generate/discover/explain.
- The web client (`app/lib/api-client.ts`) injects the bearer token per request (read fresh from the
  current Supabase session), and on a **401 it refreshes the session once and retries** exactly once;
  if refresh fails it signs out. It also injects a `traceparent` header. CORS exposes `Retry-After`.
- **Public (no JWT):** `GET /health`, `GET /ready` (DB `SELECT 1`; 200 ready / 503 not_ready),
  `GET /feature-flags`. Everything else is JWT-protected.
- RLS: `get_db` binds the session to the JWT identity so Postgres RLS scopes rows to the caller —
  defense-in-depth beneath app-layer `WHERE user_id=…`. A test cannot read/mutate another user's data.

### LLM cost guard (gates `POST /generate`, `/discover`, `/discover/accept`, `/explain`)
Gate chain order (`app/quota.py:QuotaGuard.check`): **email-verified → rate-limit → daily-cap →
global-budget**. First failure wins. A test driving these endpoints repeatedly WILL trip these:

| Gate | Trigger | Response |
|---|---|---|
| email-verified (3.7.1) | `email_verified` false on JWT | **403** `{"code":"email_unverified"}` |
| rate-limit (3.3.2) | > `RATE_LIMIT_PER_MIN` (default **10**) gated LLM calls per user per rolling 60s, counted across ALL kinds | **429** `{"code":"rate_limited"}` + `Retry-After` (seconds) |
| daily-cap (3.2) | per-user, per-kind daily count `>= cap` | **429** `{"code":"daily_cap_reached","kind":"generate\|discover\|explain"}` |
| global-budget (3.4) | global successful-call count for the UTC day `>= GLOBAL_DAILY_BUDGET` (default **1000**) | **429** `{"code":"daily_limit_reached","message":"Daily limit reached, please try again tomorrow."}` |

- **Daily caps** (per kind): server defaults `generate=20`, `discover=10`, `explain=50`; hard server
  maxima `generate=50`, `discover=30`, `explain=100`. Per-user override via `user_settings` keys
  `daily_cap_generate` / `daily_cap_discover` / `daily_cap_explain` (clamped to the max). A test
  that wants to NOT hit caps should stay well under the rate limit (10/min) — the per-minute limiter
  trips first and is the most likely false-failure in a fast script.
- **Day-0 signup-abuse clamp (3.7.2):** a brand-new account (profile `created_at` == current UTC
  day) gets `generate` cap clamped to `NEW_ACCOUNT_DAY0_GENERATE_CAP` (default **5**). A freshly
  created staging test user can only generate **5 times** on day 0 before `daily_cap_reached`.
- **Increment-on-success only:** counters bump only after a successful provider call
  (`record_success`), so failed/blocked calls don't burn quota. `generate` additionally skips the
  count when the call produced zero cards (S11 — blank-only input).
- **Counters are per-UTC-day** and **per-process in-process** for the rate limiter + discover cache
  (single Cloud Run instance assumption). A multi-instance staging deploy under-counts the rate
  limit (each replica its own window) — relevant if validation asserts exact 429 timing.

### Concurrency cap / transient-provider backoff
- `app/llm_runner.py`: a process-global semaphore (`LLM_MAX_CONCURRENCY`, default **4**) bounds
  in-flight provider calls; over the cap a request waits up to 5s then → **503**
  `{"code":"server_busy","message":"The server is busy, please try again in a moment."}` +
  `Retry-After: 1`. The SAME 503 renders a persistent provider 429/5xx (`LLMTransientError`).
- The web `ApiError` parses `{status, code, message, retryAfter}` and the UI surfaces friendly states
  for `email_unverified` / `rate_limited` / `daily_cap_reached` / `daily_limit_reached` / `server_busy`.

### E2E / zero-LLM seam
- When `LLM_PROVIDER=fake`, a test-only router (`app/testing.py`, prefix `/__test__`) is mounted
  (`GET /__test__/llm-calls`, `POST /__test__/generate`, `GET /__test__/debug-error`). It is **never**
  mounted for a real provider. Staging runs a real provider, so these routes are absent there. The
  CI E2E uses `FakeLLM` (deterministic, zero network) to prove zero real LLM calls.

---

## Endpoints (the learning loop)

### Languages — `app/routers/languages.py` (web: `app/lib/languages.ts`, `proficiency.ts`, `cefr.ts`)
- **GET `/languages`** → `list[LanguageOut]` `{id:int, name, code:str|null, vowelized:bool}`, oldest
  first. Web: `useLanguagesQuery` (key `['languages']`).
- **POST `/languages`** body `LanguageCreate` `{name (min_length 1), code?:str|null, vowelized?:bool}`
  → **200** `LanguageCreateOut` = `LanguageOut` + `created:bool`. **Idempotent** on UNIQUE
  `(user_id, name)`: `created=false` returns the existing row unchanged (S3 — re-add must not reset
  proficiency). Empty `name` → **422**. Web: `useAddLanguage` — on `created` AND a non-default
  starting `band`, follows up with `PUT /proficiency/{id}` (CEFR is NOT on the create body); a failed
  band PUT is soft (`bandError`, S12). **CEFR level is set via proficiency, not languages.**
- **PATCH `/languages/{language_id}`** body `LanguageUpdate` (all optional: `name` min_length 1,
  `code` nullable to clear, `vowelized`) — partial update (`exclude_unset`). 404 if not the user's,
  422 on validation. (No web hook calls PATCH directly in the reviewed libs.)
- **DELETE `/languages/{language_id}`** → **204** (cards/proficiency cascade). 404 if not the user's.
  Web: `useRemoveLanguage`. Staging selector: each row has a `Remove <name>` button.

### Proficiency / CEFR — `app/routers/proficiency.py` (web: `app/lib/proficiency.ts`)
- **GET `/proficiency/{language_id}`** → `ProficiencyOut` `{score:float, band:str (A1..C2),
  progress:float 0..1}`. 404 if not the user's. Web: `useProficiencyQuery`.
- **PUT `/proficiency/{language_id}`** body `ProficiencyUpdate` `{score?:float}` XOR `{band?:str}` —
  **exactly one** (model validator; supplying both/neither → 422). `score` clamped, `band` mapped to
  band lower-bound score. 404 / 422. Web: `useSetProficiencyBand` (sends `{band}`); also the
  add-language band follow-up. CEFR bands: `A1 A2 B1 B2 C1 C2` (`cefr.ts`, mirrors backend).

### Generate — `app/routers/generate.py` (web: `app/lib/generate.ts`)
- **POST `/generate`** body `GenerateRequest` `{language_id:int, words:list[str]}` →
  `list[GeneratedCardModel]` `{direction, front, back, used_words:list[str],
  word_explanations:dict|null, gen_level:float|null}`. **Nothing persisted** — previews only.
  - **Validation:** `words` `min_length 1` (empty `[]` → **422**, S11) and `max_length =
    MAX_WORDS_PER_REQUEST` (over-limit → **422**, surfaced as `maxItems`). Blank-only entries are
    dropped server-side and yield zero cards (no quota burn). 404 if language not the user's.
  - **Cost guard:** metered as `generate` (enforced up front via dependency). Day-0 cap (5) and rate
    limit (10/min) apply.
  - **S7 coverage guard:** the provider's `used_words` is verified against the actual sentence +
    requested vocab; phantom words are stripped, so returned `used_words` may be a subset.
  - Web: `useGenerate`; `WORDS_PER_REQUEST_CAP` read from `schemaLimits.generateWordsMaxItems`
    (client blocks before the 422). Returns a flat list; `groupSentences()` re-pairs recognition +
    production by sentence text for display.

### Save cards — `app/routers/cards.py` (web: `app/lib/generate.ts`)
- **POST `/cards/save`** body `SaveCardsRequest` `{language_id:int, cards:list[GeneratedCardModel]}`
  → `list[CardOut]` `{id, language_id, direction:str|null, front, back, used_words:list|null,
  word_explanations:dict|null, gen_level:float|null, saved:bool, due:datetime|null}`. Persists the
  selected previews (each gets fresh FSRS state, `saved=true`, due now), commits. 404 if language not
  the user's. **No cost guard** (no LLM call). Web: `useSaveCards` → invalidates `['review']`.

### Review / grade (FSRS recognition + production) — `app/routers/review.py` (web: `app/lib/review.ts`)
- **GET `/review/due?language_id=<int>`** → `DueResponse` `{new:list[CardOut], due:list[CardOut]}`
  split into never-reviewed vs previously-seen. Batch sizes honor per-user settings
  `daily_new_limit` / `daily_total_limit` (fallback to `lengua_core` config defaults). Web:
  `useDueQuery` (key `['review','due',languageId]`); the batch is a client-side snapshot (grading
  does not refetch mid-session). Staging selector: `review-counts` testid OR `empty-state`.
- **POST `/review/{card_id}/grade`** body `GradeRequest` `{rating:int, ge 1 le 4}` (1=Again 2=Hard
  3=Good 4=Easy; out-of-range → **422** at the schema) → `GradeResponse` `{card_id, due:datetime,
  score:float, score_changed:bool}`. Atomic: FSRS reschedule + review-log insert + proficiency nudge,
  one commit. 404 if card not the user's; 422 if the card has no FSRS state. **Recognition vs
  production** are two separate cards (separate FSRS state, scheduled independently); both are graded
  through this one endpoint. Web: `useGradeCard` (does NOT invalidate the due query by design).

### Explain (tap-a-word) — `app/routers/explain.py` (web: `app/lib/review.ts`)
- **POST `/explain`** body `ExplainRequest` `{word (min 1), sentence (min 1), translation,
  language_id}` → `ExplainResponse` `{word, explanation}`. **Cache-aware:** a hit on the card's stored
  `word_explanations` makes NO provider call (free — no gate, no count); only a cache **miss** is
  gated/counted as `explain`. 404 / 422. Web: `useExplainWord` (key `['explain',languageId,word]`,
  `staleTime: Infinity`, seeded from the card's pre-generated note when present). Word key uses
  `bareWord()` strip-chars mirroring `lengua_core.cards.STRIP_CHARS`.

### Discover — `app/routers/discover.py` (web: `app/lib/discover.ts`, `settings.ts`)
- **POST `/discover`** body `DiscoverRequest` `{language_id:int, count:int (default 5, ge 1 le 20),
  topic?:str|null, fresh:bool (default false)}` → `DiscoverResponse` `{words:list[str]}`. Preview of
  new words the learner doesn't already know — **nothing persisted**. **Cache-aware** (reuse window
  `DISCOVER_REUSE_WINDOW_SECONDS`, default 300): a repeat for the same `(language, topic, count)` is
  served from cache (no provider call, no gate, no count); `fresh:true` bypasses the cache (S8).
  Metered as `discover` only on a cache miss. `count` outside [1,20] → **422**. 404 if language not
  the user's. Web: `useDiscover`; `count` bounds from `schemaLimits.discoverCount{Min,Max,Default}`;
  default count from the `discover_count` setting.
- **POST `/discover/accept`** body `DiscoverAcceptRequest` `{language_id:int, words:list[str]
  (min_length 1)}` → `list[CardOut]`. **Generates AND saves** real cards (reuses the generate path);
  empty `words` → **422**. Metered as **`generate`** (NOT discover) and eagerly enforced — so it is
  subject to the generate daily cap + day-0 clamp + rate limit. 404 if language not the user's.

### Settings — `app/routers/settings.py` (web: `app/lib/settings.ts`)
- **GET `/settings`** → `SettingsOut` `{values: {key: str|null}}` (full map). Web: `useSettingsQuery`
  (key `['settings']`).
- **PUT `/settings`** body `SettingsUpdate` `{values: {key: str|null} (min_length 1)}` — merges keys,
  a **`null` value DELETES a key** (S10), returns the full updated map. **Server-side validation
  (422, S9):** typed numeric keys (`daily_new_limit`, `daily_total_limit`, `discover_count`) are
  bounds-checked AND cross-field `daily_new_limit <= daily_total_limit` is enforced in the service. At
  least one key required. Web: `useUpdateSettings` (writes the returned map straight to cache);
  client also pre-validates (`daily_new_limit` 1–100, `daily_total_limit` 1–500, `discover_count`
  from schema bounds). Known keys: `daily_new_limit`, `daily_total_limit`, `discover_count`, plus the
  cost-guard caps `daily_cap_generate/discover/explain`. Staging selectors: `Daily new cards` label,
  `Save settings` button.

### Account (export + hard delete) — `app/routers/account.py` (web: `app/lib/account.ts`)
- **GET `/account/export`** → `AccountExport` `{profile:{id,plan,created_at}|null, languages[],
  cards[], reviews[], proficiency[], settings:{key:str|null}}` with
  `Content-Disposition: attachment; filename="lengua-export.json"`. Scoped to `current_user` (no
  user-id param). Omits `llm_usage` + auth email. Web: `useExportAccount` → `downloadJson`.
- **DELETE `/account`** → **204** no body. Two-step hard delete (S1): (1) delete `profiles` row on a
  **privileged RLS-bypassing** session — cascades languages/cards/reviews/proficiency/user_settings/
  llm_usage via `… → profiles` ON DELETE CASCADE — **then** (2) delete the Supabase `auth.users` row
  via the service-role Admin API. Domain data erased first so a later auth-delete failure leaves NO
  orphaned content. Both steps idempotent; partial failure → **502** `{"detail":"Account deletion did
  not complete. Please retry."}` (retryable, never a false 204). No user-id param — can only delete
  your own account. Web: `useDeleteAccount` (then `signOutLocal()` — no network logout since the user
  is gone); confirm phrase `delete my account`. **This is the highest-risk endpoint to exercise on
  staging — it is irreversible and removes the test user's auth account + all data.**

### Identity — `app/routers/me.py` (`/me`)
- **GET `/me`** → `MeOut` `{id:uuid, email:str|null, email_verified:bool, plan:str,
  languages:[{language_id, name, code, score, band, progress}]}`. The JWT smoke-protected identity +
  per-language proficiency overview. Useful as a cheap authed health/identity probe in validation.

### Not part of the core loop (noted for completeness)
- **GET `/feature-flags`** → `{name: bool}` (public, no JWT). Web: `feature-flags.ts`.
- **GET `/experimental/word-of-the-day`** → flag-gated (`word_of_the_day` flag); **404 when off**
  (default off everywhere), still requires JWT (401 before the 404 gate). Ships dark.

---

## Likely failure points for a staging validation
1. **Rate limit (10/min) trips before anything else** for a fast script hitting
   generate/discover/explain — expect `429 rate_limited` + `Retry-After`. Throttle or honor the header.
2. **Day-0 generate cap = 5** for a freshly created test user → `429 daily_cap_reached kind=generate`
   after 5 generates on the signup UTC day. Use a pre-existing (established) user, or expect this.
3. **Unverified email → 403 email_unverified** on the first LLM call. The staging test user MUST be
   email-verified (the live e2e uses a seeded `demo@lengua.test`).
4. **`POST /generate` with empty/blank-only words → 422** (S11) — not a 200 with empty list.
5. **`/discover/accept` is metered as `generate`** (not discover) — it consumes the generate cap and
   does a real LLM call + save. Easy to mis-attribute when reasoning about quota.
6. **`PUT /proficiency` requires exactly one of score/band** → 422 if both/neither.
7. **`PUT /settings` cross-field** `daily_new_limit > daily_total_limit` → 422 (S9); `null` deletes (S10).
8. **`DELETE /account` is destructive + irreversible**; a partial failure is a retryable 502, not 204.
9. **Discover/explain cache hits are free and not counted** — a validation asserting a quota increment
   on a repeat call will be wrong unless it sends `fresh:true` (discover) or a novel word (explain).
10. **`server_busy` 503** (concurrency cap 4) under parallel load — a friendly retryable, not a 5xx bug.
11. **`/__test__/*` routes exist only under `LLM_PROVIDER=fake`** — absent on real-provider staging.
