# Live-Staging Validation & Triage — Lengua

**Date:** 2026-06-30 · **Scope:** live-staging correctness now (fixes deferred until approved).
**Env:** web `https://lengua-staging.vercel.app` (Vercel) → API `lengua-api-staging` (Cloud Run, GCP
project `lengua-prod`, region `europe-west1`, revision `00005-tsr`, min=0/max=1) → Supabase
`rydclyotzdwcbbeyitcx`. Demo account: `demo@lengua.test` / `demo-password-123`.

**How produced:** a 50-agent find-only workflow (`staging-triage`) — one agent exercised every API
endpoint as the demo user, a second drove headless Chromium through 8 UI flows (screenshots in
`scratchpad/staging-shots/`), 12 read-only finders (one per app slice) hunted problems, each candidate
went through adversarial verification, then synthesis. **35 candidates → 25 kept (10 refuted).**
Supplemented by direct `gcloud`/CLI inspection of the running instance. **No fixes were applied.**

## Confirmed working on live staging
- Full core loop end-to-end against **real Groq**: login → generate → save → review (reveal + 4-button
  grade) → discover → settings → languages → account-export. All 8 UI flows passed.
- Auth: Supabase login → ES256 JWT → API JWKS verification (`/me` 200, `email_verified`). Every API
  call carried `Authorization: Bearer` + a valid W3C `traceparent`.
- CORS correctly bound to the Vercel origin (`Access-Control-Allow-Origin`, `Allow-Credentials: true`).
- Feature-flag kill-switch honored (`word_of_the_day=false`). No cross-tenant leakage, no auth bypass,
  no real-LLM overspend observed.

## Live observability (verified via CLI, 2026-06-30)
The running instance has `SENTRY_DSN_API`, `OTEL_EXPORTER_OTLP_ENDPOINT`, `OTEL_EXPORTER_OTLP_HEADERS`,
and `CORS_ALLOW_ORIGINS` all set — error tracking + trace export are live.
- **Logs (CLI-readable):**
  `gcloud logging read 'resource.type="cloud_run_revision" AND resource.labels.service_name="lengua-api-staging"' --project=lengua-prod --freshness=1h --limit=20 --format='value(timestamp,severity,jsonPayload.method,jsonPayload.path,jsonPayload.status,jsonPayload.latency_ms,jsonPayload.trace_id)'`
  returns structured per-request logs. Add `AND severity>=ERROR` for failures; correlate by `trace_id`.
- **Traces:** trace_ids appear in the logs; the full waterfall lives in the OTLP backend UI (not CLI).
- **Sentry:** errors captured; viewed in the Sentry UI (note **S5** — staging is mistagged
  `environment=production`). `sentry-cli` is installed but reading issues needs an auth token.
- ⚠️ **To investigate (S21):** recurring **WARNING-severity** log entries appear during normal
  operation (seen 05:39–05:42Z) whose message did not surface in the default projection — diagnose
  during the fix pass (pull a full entry: add `severity=WARNING --format=json`).

### Executive summary

- **Core loop works end-to-end on live staging.** All 8 UI flows (login, generate, save, review,
  discover, settings, languages, account-export) passed against real Groq; all 20 API calls carried a
  valid `Authorization: Bearer` JWT and W3C `traceparent`; CORS is correctly bound to
  `https://lengua-staging.vercel.app`; the feature-flag kill-switch (`word_of_the_day=false`) is
  honored. No functional defect blocks the happy path.
- **One high-severity correctness/compliance bug:** `DELETE /account` relies on an
  `auth.users → profiles` cascade that **does not exist** on the Alembic-built staging DB (profiles has
  no FK to auth.users), so deleting an account orphans all of that user's
  languages/cards/reviews/proficiency/settings/llm_usage forever while the API returns 204 — a
  right-to-erasure failure that also ships to prod.
- **Top mediums:** the "Continue with Apple" button is live but Apple isn't enabled in Supabase, so it
  dead-ends users on a raw 400 JSON page; re-adding an existing language with a non-A1 starting level
  silently **resets that language's CEFR score** (data loss); there is **no CD seed step**, so a
  reviewer opening staging lands on an empty deck with no RTL/Hebrew deck and cannot validate review or
  RTL parity; and web Sentry mistags staging events as `environment=production` at 100% trace sampling.
- **The rest are low/info:** review walks NEW cards before DUE (UX), `used_words` is trusted from the
  LLM (chips/known_words can overstate coverage; an accepted word can get no card), Discover
  reroll/empty-retry are defeated by the reuse cache, settings/review-limit validation is client-only,
  missing security headers, Retry-After unreadable cross-origin, public `/docs`, etc.
- **Recommended FIX ORDER (live-staging-correctness scope):** (1) **S1** add the
  `profiles.id → auth.users(id) ON DELETE CASCADE` migration + defensive profile delete (data erasure);
  (2) **S4** run `seed_e2e.py` against staging so review + RTL are actually testable; (3) **S2** set
  `VITE_OAUTH_PROVIDERS=google` and redeploy to disable the broken Apple button; (4) **S3** skip the
  proficiency PUT for an already-existing language; (5) **S5** wire `VITE_SENTRY_ENVIRONMENT`; (6) batch
  the remaining low/info correctness + cosmetic fixes (S6–S20).
- Nothing here indicates real LLM spend, cross-tenant leakage, or auth bypass — all remaining issues are
  self-scoped to the caller's own data or are UX/observability/hardening gaps.

### Triage table

**Status legend:** `fixed` = code merged to `main` **and auto-deployed to live staging** (CD
`DEPLOY_ENABLED=true`) **and re-validated green** on 2026-06-30 (see Re-validation results at the
bottom). `paused (PR #n)` = fix PR open, held for owner review (merging it auto-deploys). `owner` =
owner action required.

| ID | Area | Severity | Status | Repro (short) | Owner | Suggested fix |
|----|------|----------|--------|---------------|-------|---------------|
| S1 | Account export/delete | High | paused (PR #91) | `DELETE /account` deletes only auth.users; profiles has no auth.users FK on the Alembic-built DB, so cascade never fires — all user data orphaned, 204 returned | agent | Add guarded Alembic migration `profiles.id → auth.users(id) ON DELETE CASCADE`; also delete profiles row in service; add erasure integration test |
| S2 | Auth & session | Medium | fixed | "Continue with Apple" is clickable but Supabase `external.apple=false`; full-nav lands user on raw 400 JSON, no error branch fires | Ben | Set `VITE_OAUTH_PROVIDERS=google` on staging+prod and redeploy (or enable Apple in Supabase / default `enabledProviders()` to `['google']`) |
| S3 | Languages / CEFR | Medium | fixed | Re-add existing language name with non-A1 starting level: idempotent POST returns existing, then PUT /proficiency resets score (e.g. B2→B1), silent "Language added" toast | agent | Detect idempotent add (200 vs 201/flag) and skip the proficiency PUT for a pre-existing language; warn "you already have X" |
| S4 | Infra / cold-start | Medium | fixed | No `seed` step in CD; live `/languages` = only Spanish(code:null), deck empty — reviewer can't validate review or RTL/Hebrew parity | Ben | Run `uv run python apps/api/scripts/seed_e2e.py` against staging DB; add idempotent `workflow_dispatch` seed job |
| S5 | Observability | Medium | fixed | Web Sentry uses `environment: env.MODE` (always "production" under `vercel build`) and hardcoded `tracesSampleRate:1.0`; staging events mistagged, 100% transactions | agent | Add build-time `VITE_SENTRY_ENVIRONMENT` (staging/prod) and `VITE_SENTRY_TRACES_SAMPLE_RATE`; default sample ~0.1 prod |
| S6 | Review / FSRS | Low | fixed | Review.tsx builds walk order `[...new, ...due]` (new first), opposite of legacy/scheduler "due first"; due reviews get buried if user quits mid-session | agent | Reverse to `[...due.data.due, ...due.data.new]` and update the comment |
| S7 | Generate → Save / Discover | Low | fixed | `used_words` trusted verbatim from LLM (card 15 lists "taza" but sentence lacks it); chips + known_words overstate coverage; accepted word can get no card | agent | Filter `used_words` to vocab words whose bare form actually appears in the sentence; flag accepted words with zero coverage |
| S8 | Discover | Low | fixed | Reroll re-sends identical body → reuse cache returns same words; empty result is also cached so "Try again" stays empty for the whole window | agent | Add a fresh/nonce flag (or exclude prior words) to bypass cache on explicit reroll; never `put()` an empty preview |
| S9 | Settings / review-limit | Low | fixed | PUT /settings has no server-side bounds/cross-field check; caller can persist daily_new_limit=100000, total=1 (total silently wins on /review/due) | agent | Validate typed keys server-side in `set_many`: enforce bounds + `daily_new_limit ≤ daily_total_limit` (422) |
| S10 | Settings | Low | fixed | PUT /settings is merge-only (minProperties≥1, no null); a written key (e.g. residual `smoke_test:""`) can never be removed via API | agent | Accept `dict[str, str|null]` and delete row on null, or add `DELETE /settings/{key}`; clean residual demo key |
| S11 | Generate → Save | Low | fixed | POST /generate with empty/blank-only words passes validation (no minItems) and still calls `record_success()`, burning a daily generate count for 0 cards | agent | Add `min_length=1` to `GenerateRequest.words`; skip `record_success()` when no cards produced |
| S12 | Languages / CEFR | Low | fixed | Add-language is two non-atomic requests; if proficiency PUT fails after POST, UI shows "Could not add language" but the language was created and list isn't invalidated | agent | Invalidate list on POST success, then PUT band separately and warn only on its failure; or accept band in POST /languages |
| S13 | Review / FSRS | Low | fixed | Recognition card's English answer rendered via `<LanguageText language>` → RTL deck shows it dir=rtl in script font; not visible (Spanish-only staging) | agent | Render recognition `back` (English) as plain text, like the production card's English front; only target text gets direction/font |
| S14 | RTL / diacritics | Low | fixed | Adding "Hebrew"/"Arabic" with blank code + vowel-marks renders LTR/Latin font with mispositioned nikkud; code is immutable after creation (PATCH only toggles vowelized) | agent | Require/infer a code when vowel-marks enabled; add `code`/`name` to LanguageUpdate; inline help for RTL codes |
| S15 | Discover | Low | fixed | Suggestions returned verbatim (`[:count]`), filtered against known_words only by prompt; weak dev model can surface already-known words | agent | Filter suggestions case-insensitively against known_words (+dedup) before caching; over-request and trim to count |
| S16 | Cost guard / 429 UX | Low | paused (PR #83) | API never sends `Access-Control-Expose-Headers`, so cross-origin SPA can't read `Retry-After`; 429/503 backoff countdown degrades to generic copy | agent | Add `expose_headers=['Retry-After']` to CORSMiddleware in app/main.py |
| S17 | Security headers | Low | paused (PR #83) | Neither API (Cloud Run) nor web (Vercel) sends X-Frame-Options/CSP/X-Content-Type-Options; `/docs` is framable; SPA clickjackable | agent | Add header middleware (HSTS, nosniff, X-Frame-Options DENY, Referrer-Policy) on API; add `apps/web/vercel.json` headers + baseline CSP |
| S18 | Infra / config drift | Low | fixed | Staging web CD `vercel deploy` (no `--prod`) ships an ephemeral preview URL; smoke checks that hash URL while stable `lengua-staging.vercel.app` may update out-of-band | Ben | **Resolved:** PR #71 added a `vercel alias set` step pointing each fresh deploy at the stable origin (`STAGING_WEB_ORIGIN`) + emitting it as the smoke target; PR #70 added the `vercel.json` SPA rewrite. Verified 2026-06-30 (deploy-check marker served fresh on the stable origin), and the 2026-06-30 e2e-staging pass ran green against `lengua-staging.vercel.app`. |
| S19 | Cost guard / 429 UX | Info | fixed | Shared DailyLimitPanel hardcodes "daily generation limit" even for a Discover/global kill-switch 429 (kind ignored) | agent | Make copy kind-agnostic or parametrize by `error.body.kind` (generate/discover) |
| S20 | Security / surface | Info | owner | `/docs`, `/redoc`, `/openapi.json` are anonymous 200 on staging and openapi lists the dark word-of-the-day route; same code ships to prod | Ben | Acceptable on staging; gate docs in prod (`docs_url=None` unless env in {local,staging}); confirm intent with owner |
| S21 | Observability | Low | fixed (benign) | Recurring WARNING-severity logs during normal operation (CLI, 05:39–05:42Z 2026-06-30); message not in default projection | agent | Pull full entries (`severity=WARNING --format=json`), identify source, fix or downgrade noise |

### Fix-pass outcomes (2026-06-30)

The live-staging correctness fix pass ran as a multi-agent worktree workflow (one agent per
file-disjoint group → PR; serial merge; pause on risky). Outcomes:

- **Merged to `main` + auto-deployed to live staging + re-validated green (2026-06-30):**
  **S2** (code default → Google-only, #85) · **S3·S12·S14** (#88 languages) · **S4** (seed workflow
  #79, dispatched ✓ — demo deck = 12 ES + 6 HE/RTL) · **S5** (#82) · **S6·S13·S19** (#86) ·
  **S7·S11** (#89 generate) · **S8·S15** (#84 discover) · **S9·S10** (#90 settings). The final batch
  (#88/#89/#90) merged in this driver pass after a fix to each: #88 dropped a demo-seed `Hebrew`
  collision in a new test; #90 reconciled the S9 write-bounds with the shipped review "blank/garbage
  daily-limit → config default" contract (range-check only parseable integers; cross-field only over
  explicitly-set limits). **S21** = **benign** (the recurring WARNINGs are Cloud Run *platform request
  logs* auto-tagged WARNING for expected 4xx — unauthenticated probes → 401, malformed `OPTIONS`
  preflight → 400; **no application defect, no code change** — and the 1h log spot-check on the
  redeployed revision showed **no WARNING+ entries** under the all-200 smoke).
- **Fix PR PAUSED for owner review** (CD is armed, so **merging either auto-deploys** — no manual
  step): **S1** (#91 — guarded Alembic `0006` adding
  `profiles.id → auth.users(id) ON DELETE CASCADE` + a profiles-first defensive delete + an erasure
  test; owner reviews — note the migration deletes pre-existing orphan `profiles` rows before
  `VALIDATE`, a deliberate GDPR remediation — then merges. **CD then runs `alembic upgrade head` on
  staging (and prod via deploy-prod) automatically**, so no manual `alembic` step is needed) ·
  **S16·S17** (#83 — CORS `expose_headers=[Retry-After]` + API security-headers middleware +
  `vercel.json` headers + baseline CSP; the auto-mode classifier held this for owner per the
  pause-on-security/CORS boundary — merging it auto-deploys the CSP to staging).
- **Owner (not done by agents):** **S2** env (`VITE_OAUTH_PROVIDERS`) + Apple enablement · **S20**
  (confirm prod `/docs` gating) — plus the Deferred list below. (**S18** stable-alias is already
  resolved — PR #71's `vercel alias set` step, verified 2026-06-30.)

Per-row `Status` cells above are now `fixed` / `paused (PR #n)` / `owner` (flipped after the
2026-06-30 re-validation — results at the bottom). Live resume state + exact remaining steps:
[`staging-fix-handoff.md`](staging-fix-handoff.md).

### Deferred / owner-gated (not fixed now)

- **CD is ARMED** (`DEPLOY_ENABLED=true`, set 2026-06-29) — every push to `main` migrates the staging
  DB + deploys API (Cloud Run) + web (Vercel) + smoke-checks; verified live on 2026-06-30. Remaining
  drift work: reconcile the Alembic-built staging schema vs the canonical `supabase/migrations` SQL
  (the source of the S1 missing FK), and confirm the stable Vercel staging alias path (S18) — owner.
- **Phase-5 observability live-verify (go-live §G):** confirm Sentry/Tempo/Mimir/Loki per-environment
  correlation end-to-end after the S5 env-tag fix; verify metrics/spans land for staging.
- **Google OAuth credentials:** owner-managed client/secret + redirect URIs in Supabase (the only
  working provider today); Apple requires a paid Apple Developer account if S2 is resolved by enabling
  rather than hiding.
- **Resend SMTP + email auth:** wire Resend for transactional/auth email and configure SPF/DKIM/DMARC
  for the sending domain — owner.
- **Mobile / compliance / launch:** store accounts, mobile packaging, privacy/right-to-erasure policy
  text (depends on S1 actually erasing data), and analytics-consent/launch sign-off — owner.

---

## Re-validation (after fixes)
Two reusable validators exist (both hit LIVE staging, so both are kept OUT of CI / the default test
runs):

- **API smoke** — `apps/api/scripts/staging_smoke.py`: non-destructively exercises every endpoint as
  the demo user and prints a PASS/FAIL/SKIP table. Run: `cd apps/api && uv run python
  scripts/staging_smoke.py` (set `STAGING_SUPABASE_ANON_KEY`; `SMOKE_INCLUDE_LLM=0` skips the
  real-Groq probes).
- **Browser pass** — `apps/web/e2e-staging/*.spec.ts` + `apps/web/playwright.staging.config.ts`:
  resilient, structure-only Playwright checks (login → dashboard, review deck/empty, generate,
  languages, settings). Run: `npm --prefix apps/web run test:e2e-staging` (override the origin with
  `PLAYWRIGHT_TEST_BASE_URL`).

After each fix merges, re-run both + spot-check `gcloud` logs, and update the item's **Status** to
`fixed` in the table above.

### Re-validation results — 2026-06-30 (revision deployed from `main` @ `2c1bb67`)

All three final fix PRs (#88/#89/#90) merged to `main` and **auto-deployed to live staging** by the
`deploy-staging` workflow (`DEPLOY_ENABLED=true`): migrate staging DB → build+push API image → deploy
Cloud Run → deploy Vercel → smoke-check, all `success`. Then both validators were re-run against the
live deployed revision:

- **API smoke** (`scripts/staging_smoke.py`, real Groq probes on): **13 passed / 0 failed / 0 skipped.**
  health, ready, feature-flags, login, `/me`, `/languages` (2 langs — Spanish + seeded Hebrew),
  `/review/due` (10 new / 2 due — seed present), `/settings` (4 keys), `/account/export` (6 sections),
  POST+DELETE `/languages` round-trip, `/discover` (3 suggestions), `/generate` (2 card previews).
- **Browser pass** (`e2e-staging`, Chromium vs `https://lengua-staging.vercel.app`): **6 passed** —
  logged-out redirect, demo login → app shell, review deck/empty-state, generate form, languages list,
  settings form.
- **Logs**: `gcloud logging read … service_name="lengua-api-staging" severity>=WARNING --freshness=1h`
  returned **no entries** (the all-200 smoke generated no 4xx WARNING noise) — consistent with S21
  being benign.

**Conclusion:** the 16 code/data findings (S2–S15, S19) + S21 + S18 are fixed and verified live on
staging. Remaining: **S1** (#91) and **S16/S17** (#83) paused for owner review (merging auto-deploys);
**S2** OAuth env/Apple enablement and **S20** (prod `/docs` gating) are owner calls.
