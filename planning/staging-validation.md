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

| ID | Area | Severity | Status | Repro (short) | Owner | Suggested fix |
|----|------|----------|--------|---------------|-------|---------------|
| S1 | Account export/delete | High | confirmed | `DELETE /account` deletes only auth.users; profiles has no auth.users FK on the Alembic-built DB, so cascade never fires — all user data orphaned, 204 returned | agent | Add guarded Alembic migration `profiles.id → auth.users(id) ON DELETE CASCADE`; also delete profiles row in service; add erasure integration test |
| S2 | Auth & session | Medium | confirmed | "Continue with Apple" is clickable but Supabase `external.apple=false`; full-nav lands user on raw 400 JSON, no error branch fires | Ben | Set `VITE_OAUTH_PROVIDERS=google` on staging+prod and redeploy (or enable Apple in Supabase / default `enabledProviders()` to `['google']`) |
| S3 | Languages / CEFR | Medium | confirmed | Re-add existing language name with non-A1 starting level: idempotent POST returns existing, then PUT /proficiency resets score (e.g. B2→B1), silent "Language added" toast | agent | Detect idempotent add (200 vs 201/flag) and skip the proficiency PUT for a pre-existing language; warn "you already have X" |
| S4 | Infra / cold-start | Medium | confirmed | No `seed` step in CD; live `/languages` = only Spanish(code:null), deck empty — reviewer can't validate review or RTL/Hebrew parity | Ben | Run `uv run python apps/api/scripts/seed_e2e.py` against staging DB; add idempotent `workflow_dispatch` seed job |
| S5 | Observability | Medium | confirmed | Web Sentry uses `environment: env.MODE` (always "production" under `vercel build`) and hardcoded `tracesSampleRate:1.0`; staging events mistagged, 100% transactions | agent | Add build-time `VITE_SENTRY_ENVIRONMENT` (staging/prod) and `VITE_SENTRY_TRACES_SAMPLE_RATE`; default sample ~0.1 prod |
| S6 | Review / FSRS | Low | confirmed | Review.tsx builds walk order `[...new, ...due]` (new first), opposite of legacy/scheduler "due first"; due reviews get buried if user quits mid-session | agent | Reverse to `[...due.data.due, ...due.data.new]` and update the comment |
| S7 | Generate → Save / Discover | Low | confirmed | `used_words` trusted verbatim from LLM (card 15 lists "taza" but sentence lacks it); chips + known_words overstate coverage; accepted word can get no card | agent | Filter `used_words` to vocab words whose bare form actually appears in the sentence; flag accepted words with zero coverage |
| S8 | Discover | Low | confirmed | Reroll re-sends identical body → reuse cache returns same words; empty result is also cached so "Try again" stays empty for the whole window | agent | Add a fresh/nonce flag (or exclude prior words) to bypass cache on explicit reroll; never `put()` an empty preview |
| S9 | Settings / review-limit | Low | confirmed | PUT /settings has no server-side bounds/cross-field check; caller can persist daily_new_limit=100000, total=1 (total silently wins on /review/due) | agent | Validate typed keys server-side in `set_many`: enforce bounds + `daily_new_limit ≤ daily_total_limit` (422) |
| S10 | Settings | Low | confirmed | PUT /settings is merge-only (minProperties≥1, no null); a written key (e.g. residual `smoke_test:""`) can never be removed via API | agent | Accept `dict[str, str|null]` and delete row on null, or add `DELETE /settings/{key}`; clean residual demo key |
| S11 | Generate → Save | Low | confirmed | POST /generate with empty/blank-only words passes validation (no minItems) and still calls `record_success()`, burning a daily generate count for 0 cards | agent | Add `min_length=1` to `GenerateRequest.words`; skip `record_success()` when no cards produced |
| S12 | Languages / CEFR | Low | confirmed | Add-language is two non-atomic requests; if proficiency PUT fails after POST, UI shows "Could not add language" but the language was created and list isn't invalidated | agent | Invalidate list on POST success, then PUT band separately and warn only on its failure; or accept band in POST /languages |
| S13 | Review / FSRS | Low | confirmed | Recognition card's English answer rendered via `<LanguageText language>` → RTL deck shows it dir=rtl in script font; not visible (Spanish-only staging) | agent | Render recognition `back` (English) as plain text, like the production card's English front; only target text gets direction/font |
| S14 | RTL / diacritics | Low | confirmed | Adding "Hebrew"/"Arabic" with blank code + vowel-marks renders LTR/Latin font with mispositioned nikkud; code is immutable after creation (PATCH only toggles vowelized) | agent | Require/infer a code when vowel-marks enabled; add `code`/`name` to LanguageUpdate; inline help for RTL codes |
| S15 | Discover | Low | needs-verify | Suggestions returned verbatim (`[:count]`), filtered against known_words only by prompt; weak dev model can surface already-known words | agent | Filter suggestions case-insensitively against known_words (+dedup) before caching; over-request and trim to count |
| S16 | Cost guard / 429 UX | Low | confirmed | API never sends `Access-Control-Expose-Headers`, so cross-origin SPA can't read `Retry-After`; 429/503 backoff countdown degrades to generic copy | agent | Add `expose_headers=['Retry-After']` to CORSMiddleware in app/main.py |
| S17 | Security headers | Low | confirmed | Neither API (Cloud Run) nor web (Vercel) sends X-Frame-Options/CSP/X-Content-Type-Options; `/docs` is framable; SPA clickjackable | agent | Add header middleware (HSTS, nosniff, X-Frame-Options DENY, Referrer-Policy) on API; add `apps/web/vercel.json` headers + baseline CSP |
| S18 | Infra / config drift | Low | needs-verify | Staging web CD `vercel deploy` (no `--prod`) ships an ephemeral preview URL; smoke checks that hash URL while stable `lengua-staging.vercel.app` may update out-of-band | Ben | Verify how stable alias updates; deploy with stable alias and smoke-check that origin (contrast deploy-prod `--prod`) |
| S19 | Cost guard / 429 UX | Info | confirmed | Shared DailyLimitPanel hardcodes "daily generation limit" even for a Discover/global kill-switch 429 (kind ignored) | agent | Make copy kind-agnostic or parametrize by `error.body.kind` (generate/discover) |
| S20 | Security / surface | Info | confirmed | `/docs`, `/redoc`, `/openapi.json` are anonymous 200 on staging and openapi lists the dark word-of-the-day route; same code ships to prod | Ben | Acceptable on staging; gate docs in prod (`docs_url=None` unless env in {local,staging}); confirm intent with owner |
| S21 | Observability | Low | needs-verify | Recurring WARNING-severity logs during normal operation (CLI, 05:39–05:42Z 2026-06-30); message not in default projection | agent | Pull full entries (`severity=WARNING --format=json`), identify source, fix or downgrade noise |

### Deferred / owner-gated (not fixed now)

- **CD arming + config-drift reconciliation:** flip `DEPLOY_ENABLED`, reconcile the Alembic-built
  staging schema vs the canonical `supabase/migrations` SQL (the source of the S1 missing FK), and
  confirm the stable Vercel staging alias path (S18) — owner (Kotlar/Ben).
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
Create reusable validators if not present: `apps/api/scripts/staging_smoke.py` (API smoke, all
endpoints, non-destructive) and `apps/web/e2e-staging/` + `apps/web/playwright.staging.config.ts`
(resilient browser pass). After each fix merges, re-run both + spot-check `gcloud` logs, and update the
item's **Status** to `fixed` in the table above.
