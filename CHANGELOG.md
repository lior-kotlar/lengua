# Changelog

The durable record of what shipped as Lengua was rebuilt from a local single-user
Streamlit app into a deployed, multi-user product (FastAPI + React + Supabase + Cloud Run).
This is the source of truth for **what is done**; open work lives in
[`planning/outstanding-work.md`](planning/outstanding-work.md) and the owner launch runbook
[`planning/go-live-activation.md`](planning/go-live-activation.md).

> The productionization ran trunk-based, one PR per task, in phase order (PRs #1 → #114), so the
> PR ranges below map to phases by merge order (the top-of-log post-close-out fixes reach #122).
> Milestones: **M1** = backend loop over HTTP;
> **M2** = multi-user (auth + RLS) with the LLM cost guard armed; **M3** = React web app at full
> parity; **M4** = deployed to staging **and** prod (staging leg live; prod leg = owner cutover).

---

## 2026-07-07 — Round-3 doable-now sweep

A third post-close-out sweep of the non-owner/prod/mobile hardening items tracked in
[`planning/outstanding-work.md`](planning/outstanding-work.md), led by the accessibility
colour-contrast pass.

- **Accessibility — WCAG 2.1 AA colour-contrast pass (#135).** The advisory axe sweep added in #127
  flagged serious `color-contrast` violations on every authenticated surface (Dashboard / Generate /
  Review / Discover / Settings — 23 nodes: primary buttons, blue links/badges, and the red/green
  tinted rating pills + status chips). Fixed at the **design-token** layer in `src/index.css`, not
  per-component: `--primary` (and `--ring`) nudged from systemBlue `#007AFF` to a deeper, same-hue
  `#006CE0` so **white-on-primary** buttons and **`text-primary` links** clear 4.5:1 in light; the
  light `--hig-red-deep` / `--hig-green-deep` text hues deepened, and the dark `--hig-red-deep` /
  `--hig-blue-deep` text hues **lifted above their vivid fill** (the "re-pointing trick" now carries
  the AA-safe text hue, not merely the vivid), so the tinted pills/chips clear AA on the dark card in
  **both themes**. The blue chips (Languages / user-menu / dashboard badges / the `tinted` button)
  moved off `bg-primary/15` onto the unchanged vivid `bg-hig-blue/15` so the deeper button-primary
  can't mute them, and the daily-limit panel's body copy dropped its `/80` opacity. The Apple-HIG
  identity is intact (same hues, deeper lightness only). The `e2e/a11y.spec.ts` sweep now **asserts
  zero serious `color-contrast`** on the swept surfaces (the `e2e` job's `@a11y` run dropped its
  `|| echo` guard) and a new browserless `src/token-contrast.test.ts` re-derives contrast from the
  real `index.css` tokens to lock **both** themes (axe only sweeps light). Residual, documented: the
  iOS-brand **solid** buttons — white-on-systemBlue (dark primary) and white-on-systemRed
  (destructive confirm) — render only in dialogs / dark mode, never on the swept light happy path, so
  they stay as the tracked brand exceptions (floored at the 3:1 UI minimum by the token test).

## 2026-07-06 — Phase 8 compliance & store (buildable code slice)

Pulling the **CI-verifiable** half of Phase 8 (compliance & store readiness) forward, ahead of the
owner-run store/prod work (App Store Connect / Play Console entry, device screenshots, publishing).
Mobile/Capacitor, prod cutover, secrets, and migrations are untouched.

- **Privacy policy (#130, 8.1.1).** Replaced the Phase-0 `docs/privacy-policy.md` stub with a
  complete **GDPR privacy policy**: data categories (account email, learning content, content sent
  for AI generation, opt-in analytics, error diagnostics, technical/local storage); **Supabase (EU)**
  as the primary store; **Google Gemini** as the production **LLM provider** (Groq dev-only); lawful
  bases (contract / consent / legitimate interest); international transfers (SCCs/adequacy) + a
  sub-processor table; retention; the full data-subject rights; and a dedicated **export / delete**
  section (in-app Account actions + the public `/delete-account` form). Controller "Lengua", contact
  `privacy@lengua.app`. Added `scripts/check_doc_links.py` (stdlib, no network) + a `docs` CI job that
  asserts every relative markdown link across `docs/**` + `README.md` + `CHANGELOG.md` resolves
  (67 links, 7 files) — the "link-check in CI" the task's verify calls for.
- **Public deletion form + legal routes (#131, 8.1.2 + 8.3.1).** The store-required public compliance
  surfaces. **API:** two intentionally-**public** endpoints behind the external deletion path Google
  Play requires — `POST /account/deletion-request` (rate-limited per email, a generic
  **non-enumerating** ack, emails a signed one-hour HMAC token) and `POST /account/deletion-confirm`
  (verifies the token, then runs the **same** two-step cascade as in-app `DELETE /account`: domain
  rows on the privileged session → the Supabase `auth.users` record). Ownership is proven by the
  emailed token, not a session, so both are exempted from the route-auth / no-guest guards (like
  `/feature-flags`). A **mailer seam** (`app/mailer.py`: `LoggingMailer` no-egress default,
  `ResendMailer` when `RESEND_API_KEY` is set) mirrors the LLM seam — no SMTP to build/test; real
  delivery activates at the owner's Resend setup (issue #103). **Web:** `/privacy` (the published GDPR
  policy), `/support`, and the public `/delete-account` form, all in a sign-in-free `StaticLayout`; a
  site footer (Privacy + Support) on every shell and Account-screen links to both. A 6-vector
  adversarial security review held (no unauthorized deletion / token forgery / body-enumeration; correct
  cascade); it also found and this PR **fixed** a latent mailer-transport-error enumeration oracle, and
  **logged** the residual low/latent DoS-amplification hardening in `outstanding-work.md`. OpenAPI +
  `api-types` regenerated.
- **Launch-blocker E2E assertions (#132, 8.2.1 + 8.2.3 + 8.2.4).** Tests only — no UI rebuilt.
  Declining analytics consent now provably loads **zero** analytics across a full authenticated
  session (not just `/login`); the in-app export download's contents are asserted **equal** to the
  `GET /account/export` response bundle (not just the filename); and in-app account deletion is
  asserted **reachable via in-app navigation only** (no external URL) and to **clear the session**.
  The gate-blocks-even-with-a-key invariant stays unit-covered in `src/lib/analytics.test.ts`, and the
  real delete cascade in the backend integration tests.
- **Store-listing & data-safety source of truth (#133, 8.4.1 + 8.7.1 + 8.2.2).** Added
  `docs/store-listing.md` as the single source both stores reference: the published URLs; the
  store-listing copy (name / subtitle / short + full description / keywords / category) capped at the
  **shorter** of the Apple/Play limits and validated in CI by `scripts/check_store_listing.py` (wired
  into the `docs` job) so one copy fits both; the **data-inventory matrix** the Apple App Privacy +
  Play Data Safety answers derive from (email / user content / analytics / crash diagnostics /
  identifiers × purpose / linked? / tracking?, tracking = No throughout); and per-processor **data
  residency**. Added a Data-residency (GDPR) record (EU regions) to `docs/runbook.md`, and updated the
  README (public deletion endpoints + public pages) + docs index. **This completes the buildable,
  CI-verifiable Phase-8 slice; everything remaining is the owner store/prod cutover.**

## 2026-07-06 — Round-2 doable-now sweep — PRs #126, #127, #128

A second post-close-out sweep clearing the last non-owner/prod/mobile items from
`planning/outstanding-work.md`: CI-only test debt, the advisory-a11y broadening, and code-comment
hygiene.

- **API tests (#126).** Landed the two account-lifecycle integration tests deferred from #123: an
  export-under-**real-RLS** test that drives `GET /account/export` through the un-overridden scoped
  `get_db` (authenticated role, Postgres RLS enforcing — not just the app-layer `WHERE user_id`
  filter) and proves A's export is scoped to A with none of B's rows; and a
  deleted-but-unexpired-token test proving a still-valid JWT for a just-deleted account reads a `200`
  **empty** bundle (never a leak or `500`) inside the stateless-JWKS `exp` window. Both are
  `@pytest.mark.integration` (live Postgres + Supabase auth), so they execute in CI's backend job.
- **a11y CI (#127).** Broadened the advisory accessibility pass beyond the static `/login` page: a
  new `@axe-core/playwright` sweep (`apps/web/e2e/a11y.spec.ts`) logs in as the seeded demo user under
  the FakeLLM e2e harness and runs axe on Dashboard / Generate / Review / Discover / Settings, logging
  + attaching violations without ever asserting. Wired into the `e2e` job as an advisory run (the
  required run `--grep-invert`s the `@a11y` tag; the advisory run is `|| echo`-guarded), so it is
  never a merge gate. Its first run surfaced serious `color-contrast` violations on every
  authenticated surface — tracked under the post-v1 accessibility-pass backlog.
- **Docs (#128).** Repointed the code-comment citations of the planning design docs deleted in
  #115/#116 (`app/quota.py` ×3, `app/repositories/__init__.py`, `lengua_core/llm/keys.py`,
  `.github/workflows/ci.yml`, `apps/web/e2e-staging/signup.spec.ts`) to the root `CHANGELOG.md` /
  self-documenting text. The applied migration `0006`'s comment is left as-is (migrations are
  off-limits even for comments). Comment-only, no behavior change.

---

## 2026-07-05 — Post-close-out hardening, perf & polish — PRs #117, #119, #121, #122

A run of agent-implemented, CI-verified PRs landed right after the planning close-out — hardening the
API boot path and the web tap-a-word / accessibility surface, then trimming the web bundle and paying
down UI-polish + test-coverage debt.

- **API (#117).** A **boot-time config guard** logs `CRITICAL` when `env ∈ {staging, prod}` and
  `SUPABASE_SERVICE_ROLE_KEY` / `SUPABASE_URL` is unset, so a misconfigured `DELETE /account`
  surfaces loudly at startup instead of failing only on the first deletion (a strict no-op for
  `local`/`ci`/`test`/`e2e`, which run without the key by design). The dark `GET /experimental/*`
  route is now **hidden from the public OpenAPI** (`include_in_schema=False`) — kept out of
  `openapi.json` and the generated `api-types` client while it ships dark, with the runtime
  404-until-flag behavior unchanged. The coverage gate is **DB-reachability-aware**: a no-DB local
  `pytest` skips the integration tests and relaxes `--cov-fail-under` (loud banner) instead of a
  false red, while CI (Postgres up) still enforces ≥80%. And the in-process rate-limiter reclaims a
  user's window entry once it empties, so its map stays **bounded** (mirroring the size-capped
  discover cache).
- **Web (#119).** Fixed a **tap-a-word bug** — the explain-word query cached by `(languageId, word)`,
  so a word recurring across cards showed the first card's explanation; the query key now includes
  the sentence/card, giving each card its own note. Accessibility: `LanguageText` / `TappableSentence`
  now emit `lang={language.code}` (WCAG 3.1.2) so screen readers pronounce foreign text correctly;
  the tap-a-word popover manages focus (move-in / restore-to-trigger); and the Languages row plus the
  dashboard tiles/quick-actions gained the app focus-visible ring.
- **Web perf (#121).** Route-level code splitting — the authenticated non-landing screens are
  `React.lazy` chunks fetched on first navigation (auth screens + Dashboard stay eager), with the
  `Suspense` skeleton around the app-shell `<Outlet />` so the nav stays mounted. Sentry now loads via
  dynamic `import()` only when a DSN is set (out of the initial bundle), stable vendor chunks
  (react + router / react-query / supabase) are split out, and the stock Vite favicon is replaced by a
  real one.
- **Web polish & test coverage (#122).** An Apple-HIG className pass on the surfaces the redesign had
  missed — the tap-a-word popover moves to the design system (`rounded-lg` / `shadow-raised`, dotted-
  underline word affordances), a `text-body` / `text-subhead` / `text-footnote` type-scale sweep across
  the auth + dialog + helper text, the Generate save bar on the shared `.frosted` utility, and
  right-aligned vowel-marks toggles. Plus coverage debt: `lengua_core.prompts` enters the gate with a
  (vowelized × level) / (known-words × topic) branch matrix, and `use-toast.ts` is carved out of the
  web `ui/` coverage exclusion with a reducer + store test.

---

## 2026-07-05 — Planning close-out (staging-leg validation) — PRs #115–#116

Validated every **as-code** and **staging-live** acceptance criterion that could be checked now
(read-only against live staging + local/CI test runs), and ticked it with evidence. **No prod
mutation, no deploy, no migration.** 17 boxes flipped to done:

- **Phase 0 — `0.7.7`**: CI secrets `GCP_REGION` + `SENTRY_ORG` present (`gh secret list`; the armed
  staging CD consumes them green).
- **Phase 2 exit gate** (as-code): no hard-coded user + route-auth 401s; app-layer **and** RLS
  cross-tenant isolation; JWT rejection (expired / forged / `alg:none`); profiles-on-first-login +
  demo-seed full loop; account cascade-delete with no orphans + auth-user removal; legacy SQLite
  import. Two DB-free suites ran locally (27 passed); the seven DB-backed suites are green in CI run
  **28715034639** (live Supabase Postgres+Auth, ≥80% branch coverage enforced).
- **Phase 6 staging leg**: Artifact Registry EU repo with SHA + `:staging` tags (`6.1.3`);
  `lengua-api-staging` Cloud Run service `Ready`, `/health` 200, 11+ retained revisions (`6.1.4`,
  `6.8.1`); Alembic history applied to the staging DB at head (`6.2.2`); the merge→staging CD steps
  (build-push, deploy, deploy-web, smoke) all green on the latest `main` deploy — run 28715034653
  (`6.6.1`, `6.6.2`, `6.6.4`, `6.6.5`); the *"merging to `main` ships staging automatically with an
  applied migration"* exit gate; and *"no secret leaks to the client + security scans pass"* (fresh
  `pnpm` build → bundle carries only the Supabase **anon** key + public URLs; gitleaks / pip-audit /
  pnpm-audit all green in CI).

Left **unticked** (unchanged): everything prod-gated (`6.1.5`, `6.2.3`, `6.7.x`, prod promotion /
rollback proof), owner dashboard/cred (all of Phase 5 live observability — Grafana/Sentry/PostHog/
uptime), owner account setup (Google/Apple OAuth, Resend SMTP + SPF/DKIM, Vercel project link,
branch protection, Dependabot), and the two remaining exit-gate clauses that need those.

Docs pruned in the same pass: deleted the resolved point-in-time staging-validation material
(`planning/staging-validation.md` + `planning/staging-validation/**` + `planning/staging-fix-handoff.md`),
slimmed the numbered design docs to implemented-status stubs, and made this changelog + `outstanding-work.md`
the single source of truth for done-vs-left.

---

## Live-staging validation & hardening (2026-06-30 → 2026-07-05) — PRs #79–#98, #100–#104

After staging went live and CD was armed (`DEPLOY_ENABLED=true`, 2026-06-29), a 50-agent live-staging
validation exercised the deployed stack (web + API + DB) as the demo user and surfaced 25
correctness/UX/hardening items; a multi-agent fix pass then landed all of them. **All 22 findings
(S1–S22) are fixed or accepted**, and the full study flow (login → generate → save → review incl.
Hebrew RTL → discover → settings → account) is verified working on live staging with no errors.

- **S1 (right-to-erasure, #91)** — guarded Alembic `0006` adds `profiles.id → auth.users(id) ON
  DELETE CASCADE` (+ orphan purge) so account deletion actually erases all user data; owner-approved,
  applied to the staging DB (`profiles_id_fkey` validated).
- **S16/S17 (#83)** — CORS `Access-Control-Expose-Headers: Retry-After`, API security-headers
  middleware (nosniff / `X-Frame-Options: DENY` / Referrer-Policy / HSTS), and a baseline CSP on the
  web tier; owner-approved.
- **S2** OAuth Google-only default · **S3/S12/S14 (#88)** language add/CEFR atomicity · **S4 (#79)**
  idempotent staging seed (demo deck = 12 ES + 6 HE/RTL) · **S5 (#82)** Sentry per-env tag + sample
  rate · **S6/S13/S19 (#86)** review order + RTL copy · **S7/S11 (#89)** used-word coverage +
  empty-generate guard · **S8/S15 (#84)** + **S22 (#97)** discover cache / known-word / vowel-mark
  dedup · **S9/S10 (#90)** settings server-side validation. **S21** diagnosed benign (Cloud Run 4xx
  platform logs). **S18** stable Vercel staging alias resolved (#71). **S20** (prod `/docs`) accepted,
  to gate before public launch.
- **Sign-up fix (#100–#104)** — live-staging register → logout → login made green by disabling email
  confirmation on staging (interim `mailer_autoconfirm=true`); the `{}`/`[object Object]` auth alert
  fixed (#102). **Prod follow-up (issue #103, owner):** real Resend SMTP on a verified domain, then
  re-enable email confirmation — must NOT ship prod with autoconfirm on.

Two reusable validators are kept in the repo (out of CI, they hit live staging):
`apps/api/scripts/staging_smoke.py` (13/0/0) and `apps/web/e2e-staging/*.spec.ts` (6/6).

---

## M3 — React web app at full parity (Phase 4) — PRs #38–#50

Delivered the full React + TypeScript (Vite) web app, closed by an end-to-end full-loop Playwright
spec:

- App shell & foundations (theming, routing, TanStack Query, Supabase client); a typed, authed API
  client generated from the OpenAPI contract.
- Auth screens with session handling; language/CEFR management.
- **Generate**, **Review** (FSRS loop, reveal + 4-button grade, tap-a-word, keyboard shortcuts),
  **Discover**, and **Settings/Account** screens.
- RTL / diacritics / complex-script rendering; cross-cutting UX + consent states; a per-user daily
  review-limit fix.
- A later Apple-HIG redesign sweep (PRs #105–#114) refreshed foundations, app shell/nav, the review
  experience, the Dashboard home screen, forms, and auth cards.

## M2 — Multi-user with the LLM cost guard armed (Phases 2 & 3)

**Phase 2 — Auth & multi-tenancy (PRs #24–#30).** Supabase JWT verification → typed `current_user`
(HS256 secret or RS256/ES256 via JWKS; `exp`/`aud` checked; expired/forged/`alg:none` rejected) with
`GET /me` and a strict CORS allowlist; per-user scoping of every query; a `profiles`-on-first-login
trigger (`plan='free'`) with no-guest enforcement; Supabase Auth config (email confirmation, password
policy, redirect allow-list, branded email templates); Postgres **Row-Level Security** with a
per-request `authenticated` DB identity (defense-in-depth beneath app-layer scoping); a one-off
legacy SQLite→Postgres history import; and account-lifecycle endpoints (`GET /account/export` +
hard `DELETE /account`).

**Phase 3 — LLM cost guard (PRs #31–#37).** Usage accounting with a server-only kill-switch privilege
model; per-user daily caps; rate limiting + an email-verified gate + a signup-abuse guard; a global
daily-budget kill-switch; a concurrency cap with backoff and a BYOK key-resolution seam;
request/token cost minimization with Discover reuse; and cost-guard observability (spans + metrics) —
proven by a **zero-paid-usage load test**.

## M1 — Backend core loop over HTTP (Phase 1) — PRs #15–#23

Ported the domain logic into a pure `lengua_core` package; put Groq/Gemini/Fake behind one
`LLM_PROVIDER` seam; built the async SQLAlchemy persistence foundation (repository → service layers);
added Alembic + the first full-schema migration and dev-user seed; exposed the complete core-loop
HTTP surface (generate / save / review / discover / explain / proficiency / settings); and added the
OpenAPI contract dump + drift test, `api-types` codegen, and the OpenTelemetry / structured-log
skeleton.

## Phase 0 — Foundations — PRs #1–#14

Stood up the monorepo (`apps/api` + `apps/web`), relocated the domain package and the legacy
Streamlit app under `apps/api` (kept runnable for reference), scaffolded the FastAPI + React/Vite
shells, shared test infra (factories, FakeLLM, test Postgres, E2E seed), the per-PR CI quality gate
(lint/types · backend + frontend tests at ≥80% coverage · build · E2E with the LLM stubbed ·
gitleaks/audit), and the autonomous build orchestration (`/run-phase` skill + `phase-task-runner`
agent). *Owner-deferred to launch: branch protection (`0.6.3`), Dependabot (`0.6.4`).*

## Phase 5 — Observability (as-code) — PRs #51–#59

The observability layer, complete **as-code** (CI-verified); the **live** half (traces/logs/metrics
rendering in Grafana, Sentry alert routing, PostHog insights, external uptime) is owner-deferred
until the dashboards/creds are wired ([go-live §G](planning/go-live-activation.md)):

- OpenTelemetry foundation; custom spans (`llm.call` / `quota.check` / `review.grade`) and
  provider-agnostic domain metrics.
- Structured, correlated logging (OTLP log export carrying `trace_id`/`span_id`/`user_id`); W3C
  `traceparent` propagation for client → API → DB / LLM trace continuity.
- Sentry error tracking (API + web, dual DSN); Grafana dashboards-as-code (RED / cost-guard /
  product / infra skeleton) with a drift test; consent-gated, PII-free PostHog product analytics.
- Alerts-as-code (5xx > 5% / 5m, p95 > 1.5s / 10m, LLM budget < 20%, uptime) + an external
  uptime-monitor descriptor and runbook health-check entries.

## Phase 6 — Infra, environments & CI/CD (M4 staging leg) — PRs #60–#78

Infra + CD **as-code**, then armed and green-verified end-to-end on the staging leg:

- `/ready` readiness probe + a digest-pinned, non-root API `Dockerfile` (CI build-run smoke).
- Per-env CORS with a no-wildcard guard; a web-bundle secret-leak audit (CI grep + a source-scan
  unit test).
- Feature flags: env default overlaid by a global `feature_flags` table, cached with a TTL so a
  toggle takes effect **with no redeploy**; a public `GET /feature-flags`; the `word_of_the_day`
  surface ships dark.
- The gated staging + prod CD pipeline (`deploy-staging.yml` / `deploy-prod.yml`) with an
  `alembic -x env=…` resolver, discrete logged migration jobs, digest-promotion to prod behind a
  `production`-environment approval, shared composite deploy/smoke actions, and a one-click
  `infra/deploy/rollback.sh`.
- The go-live runbook. CD was then armed (`DEPLOY_ENABLED=true`) and the staging leg brought green:
  JWKS env fix, SPA rewrite, stable-alias CORS smoke, the Supabase session-pooler DB-URL fix
  (IPv6→IPv4), and env-var `#`-comment handling. **The prod leg (gated promotion) remains an
  owner cutover.**

---

## Locked decisions & rationale (preserved)

Design rationale worth keeping as the numbered `planning/0X-*.md` design docs are retired into
implemented-status stubs:

- **Stay-free-by-design.** Every dependency (LLM, DB, hosting, observability) is chosen to fit a
  viable free tier — the reason the whole cost-guard + provider-choice architecture exists.
- **LLM provider.** Pluggable behind one interface, picked by `LLM_PROVIDER`: **Groq** free tier for
  all dev/CI, **Fake** for E2E (zero real calls), and **Gemini** as the intended prod/launch default
  reachable by a single env-var flip **with no code change**. **BYOK was rejected for v1** in favor
  of an operator-funded, capped key (the reason a cost guard is needed at all); BYOK remains the
  growth escape hatch.
- **Ship all platforms together.** The web app is built first *because Capacitor wraps it*, but the
  launch gate requires web + iOS + Android ready simultaneously.
- **v1 scope.** Keep all current features (Generate, Review, Discover, Settings, multi-language,
  vowel marks, tap-a-word, Anki import). `profiles.plan` is a deliberate **paid-ready seam with zero
  payment code in v1**. **Local** review reminders are in v1; **server** push is out. Offline is
  online-first at launch, with a fast-follow that caches the due batch and **queues review grades
  offline** (TanStack Query persistence + background flush; generation stays online-only) — the
  stated reason TanStack Query was chosen. TTS is post-v1, on-device/browser first.
- **Backend host = Cloud Run**, chosen over Render/Fly: Render's free web services sleep ~15 min with
  a slow wake (bad for a mobile app's first request of the day); Cloud Run scales to zero but wakes
  fast with a large free request allowance. **Fly.io is the fallback.**
- **SLOs.** API availability target **99.5% monthly** (cold starts count); a p95 latency SLO on
  non-LLM routes; **measure but do NOT SLO** the LLM/provider latency (provider latency dominates);
  define an error budget + burn-rate alerts once there is real traffic.
- **Architecture invariants.** Routers → services → repositories → DB, with repositories the only
  layer that touches the DB; the LLM provider seam is a config flip, never a code change, and
  fails fast at boot on a missing key.
- **Compliance is a launch blocker** (in-app account deletion + published privacy policy + store
  data-safety forms), not a nice-to-have. **EU** Supabase region; full GDPR posture (consent +
  export + delete); PostHog anonymized + consent-gated from v1.

## Not yet done (see `planning/outstanding-work.md` + `planning/go-live-activation.md`)

**M4 prod cutover** (owner — go-live §F: prod DB schema + IPv6→session-pooler swap, prod Auth/CORS,
`production`-environment reviewer + digest promotion, web prod, rollback drill) · **Phase 5 live
observability** (owner — Grafana/Sentry/PostHog/uptime dashboards + alert channels) · **Phase 7**
mobile (Capacitor, store accounts, on-device validation) · **Phase 8** compliance & store (real
privacy policy, data-safety declarations, listings) · **Phase 9** launch. Plus owner setup: Google/
Apple OAuth, Resend SMTP + SPF/DKIM/DMARC (+ re-enable prod email confirmation, issue #103), branch
protection, Dependabot, prod `/docs` gating.
