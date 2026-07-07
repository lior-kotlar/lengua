# Outstanding work — what's left

**What this is:** the single live list of everything in Lengua that is **not complete** — the
launch path, owner-blocked items, and known engineering gaps. Whenever something incomplete is
noticed (in any session), append it here with *where* + *status*.

Everything **done** (phases 0–6, M1–M3, the M4 staging leg, the 22 resolved live-staging findings,
and the locked decisions) is recorded in [`../CHANGELOG.md`](../CHANGELOG.md). The owner launch
runbook (a `verify:` gate on every step) is [`go-live-activation.md`](go-live-activation.md);
owner-only repo hardening is [`owner-deferred-tasks.md`](owner-deferred-tasks.md).

Conventions: ☐ open · 🔒 blocked-on-owner · ◐ as-code-done / live-owner-deferred.

---

## ★ What's left to launch — single source of truth

- **(A) M4 prod cutover** — owner ([`go-live-activation.md`](go-live-activation.md) §F). Apply the
  prod DB schema incl. migration `0006` (⚠ first swap `SUPABASE_PROD_DATABASE_URL` to the IPv4
  **session pooler**, port 5432 — the direct IPv6 host fails on GitHub runners); prod Supabase Auth +
  API CORS = exact prod origins; create the GitHub **`production` environment + required reviewer**,
  then promote the exact staging-validated **image digest** (no rebuild); deploy web prod; run the
  rollback drill (≥2 revisions retained).
- **(B) Phase-5 live observability** — owner ([`go-live-activation.md`](go-live-activation.md) §G).
  Traces in Tempo + per-route p95 in Mimir; logs in Loki + Tempo→Loki jump; RED / cost-guard /
  product / infra dashboards non-empty; Sentry issues ↔ trace; Grafana + Sentry alert rules firing
  to a real channel; external uptime monitor; PostHog funnel / D1-D7 retention / feature usage. The
  as-code is all committed (`infra/grafana/**`, `infra/uptime/**`, the exporters + alert rules);
  what's left needs **live Grafana/Sentry/PostHog/uptime creds + the deployed service** (staging is
  live now, so most of this is unblocked once the dashboards are wired).
- **(C) Phase 7 — mobile** ([`tasks/phase-7-mobile.md`](tasks/phase-7-mobile.md)). Paid store
  accounts (Apple $99/yr — start early; Google Play $25), Capacitor native projects + plugins,
  OAuth-in-webview, OTA channel, on-device full-loop validation.
- **(D) Phase 8 — compliance & store** ([`tasks/phase-8-compliance-store.md`](tasks/phase-8-compliance-store.md)).
  The **buildable/CI-verifiable code slice is being pulled forward** (see `CHANGELOG.md`): ◐ 8.1.1
  real GDPR privacy policy done (#130) with a `docs` link-check CI job; ◐ 8.1.2 + 8.3.1 the public
  `/delete-account` form + `/privacy` + `/support` routes + the request→confirm→cascade API done
  (#131). ◐ 8.2.1 + 8.2.3 + 8.2.4 launch-blocker E2E assertions (consent → no analytics across a full
  session; export download == `GET /account/export`; in-app delete via in-app nav only + clears the
  session) done (#132). ◐ 8.4.1 + 8.7.1 + 8.2.2 `docs/store-listing.md` (data-inventory matrix +
  store-listing copy with a CI character-limit check + per-processor EU residency) + the runbook
  data-residency record done (#133). **The buildable/CI-verifiable Phase-8 slice is now complete.**
  **Owner-blocked (store/prod), all requiring the paid store accounts + the deployed prod app:**
  Apple App Privacy labels (8.4.2) + encryption declaration (8.4.3), Play Data Safety (8.5.x), age
  ratings (8.6), store-console listing entry (8.7.2/8.7.3), device screenshots (8.8), and the
  TestFlight/Play closed tests (8.9) — each derives from the docs above but needs the live consoles.
  - **Placeholder to confirm at launch:** the privacy policy + `/support` + `/delete-account` use
    `privacy@lengua.app` and `https://lengua.app`. Before public launch the contact address must
    point to a **monitored inbox** and the host must match the real prod web domain (owner cutover).
- **(E) Phase 9 — launch** ([`tasks/phase-9-launch.md`](tasks/phase-9-launch.md)). Cross-platform
  prod smoke, store submit → promote, custom-domain cutover, 48h watch; finalize the runbook On-call
  + Store-release sections.
- **(F) Owner setup still open** ([`owner-deferred-tasks.md`](owner-deferred-tasks.md)). Resend custom
  SMTP + SPF/DKIM/DMARC on a verified domain → **re-enable prod email confirmation** (issue #103, the
  interim staging `mailer_autoconfirm=true` must NOT ship to prod); Google (2.1.2) + Apple (2.1.3)
  OAuth + `VITE_OAUTH_PROVIDERS` per env; branch protection (0.6.3) + Dependabot (0.6.4) at launch;
  gate prod `/docs` `/redoc` `/openapi.json` (S20); Vercel→Cloudflare host migration
  ([`go-live-activation.md`](go-live-activation.md) §H, plan-only).
- **(G) Post-v1 / post-launch backlog** (not blocking launch): offline review + sync (cache due
  batch, queue grades offline, flush on reconnect — the stated #1 post-launch item); server push
  notifications (FCM/APNs; v1 uses on-device local reminders); TTS audio (on-device first); streaks /
  gamification; import/export & shared decks (beyond Anki import); UI internationalization (the app's
  own UI is English-only); spaced-repetition insights (progress charts, review forecast); admin /
  support tooling (support views, abuse review, manual budget override); accessibility pass —
  colour **contrast** is now WCAG 2.1 AA and CI-gated across the authenticated surfaces in both
  themes (round-3, see CHANGELOG; `e2e/a11y.spec.ts` asserting + `src/token-contrast.test.ts`), with
  screen-reader labels and font scaling still remaining. **Watch:** confirm Supabase free-tier
  idle-pausing / project limits at setup.

---

## Known engineering gaps / tech-debt (open)

Small, non-blocking items in shipped code — close when the relevant area is next worked:

- **Prod DB is Supabase-only by construction.** The API assumes the `authenticated` role per request
  (RLS), so the runtime `DATABASE_URL` **must** be a Supabase-provisioned Postgres (has the
  `authenticated` role + `auth.uid()`); a bare Alembic-only Postgres 500s on the role switch. Also
  asyncpg's prepared-statement cache breaks against the Supabase **transaction** pooler (6543) —
  use the **session** pooler (5432) or `statement_cache_size=0`. Confirm prod `DATABASE_URL` before
  the cutover (folds into (A)).
- **Runtime service account.** The hand-deployed staging revision uses the **default compute SA** —
  move Cloud Run to a dedicated runtime SA with `secretmanager.secretAccessor` **only** (6.1.6).
- **Coverage carve-outs.** `lengua_core/models.py`, `app/settings.py`, the whole
  `legacy_streamlit/`, and the web `src/main.tsx` + the `src/components/ui/**` presentational
  primitives (`.tsx`) are excluded from the 80%
  gate; ~20 backend modules are `@pytest.mark.integration` (auto-skip offline), so the 80% gate is
  only truly enforced in CI with Postgres up. A local run without a reachable DB now auto-relaxes
  `--cov-fail-under` to 0 with a loud banner (`tests/conftest.py::pytest_configure`) instead of
  false-failing red — so local coverage still ≠ CI coverage, but a DB-less run is no longer a false red.
- **Base-image digest pin needs periodic refresh** (`apps/api/Dockerfile`) — bump the `python:3.12-slim`
  digest during deploy hardening or via Dependabot once enabled. *(Last refreshed 2026-07-07 →
  `sha256:423ed6ab…`, round-3; the tag drifts, so re-check periodically.)*
- **Doc stubs:** `docs/privacy-policy.md` is now the real GDPR policy (Phase 8, #130); the runbook's
  **On-call** + **Store-release** sections are still finalized at launch (Phase 9).
- **Public deletion endpoint — DoS hardening (low / latent, #131).** The adversarial security review
  of `POST /account/deletion-request` confirmed the security invariants hold (no unauthorized delete,
  no token forgery, no response-body enumeration, correct cascade) and that the mailer-transport 500
  oracle is fixed. Three residual **low, latent** hardening items remain (all safe at the current
  <200-user scale — 1:1 amplification today): (1) ~~`find_auth_user_id_by_email` pages the GoTrue
  Admin API linearly~~ **DONE** (round-3, #138): an indexed `SELECT id FROM auth.users WHERE
  lower(email) = …` on the privileged session is tried first (removing the unauthenticated-endpoint →
  Admin-API fan-out), falling back to the Admin API on any DB error so a missing owner-role grant
  can't regress the flow; (2) ~~add a **per-IP / global** rate limit on that endpoint~~ **DONE**
  (round-3, #137): a per-IP cap (30/hour, `X-Forwarded-For`-aware) now guards the endpoint alongside
  the per-email cap; (3) `InProcessRateLimiter` (`app/ratelimit.py`) only reclaims a key's entry on
  re-hit, so one-shot distinct keys (attacker-varied emails) accumulate — cap the map size or add a
  TTL sweep. Do (3) when the user base approaches store-scale (folds into the same shared-store move
  as the process-local rate-limiter / discover-cache).
- **Stale code-comment doc citation (migration only).** The applied migration
  `migrations/versions/20260630_0006_*.py` still cites the deleted `staging-validation.md` (finding
  S1). Migrations are off-limits even for comments, so this one lingers by design; every other stale
  citation (`app/quota.py`, `app/repositories/__init__.py`, `lengua_core/llm/keys.py`,
  `.github/workflows/ci.yml`, `e2e-staging/signup.spec.ts`) was repointed to `CHANGELOG.md`.
- **Observability follow-ups** (do alongside (B)): export the browser client span to Tempo (today the
  web only injects `traceparent`); unify web-Sentry ↔ Tempo by `trace_id`; add a `proficiency_cefr_band`
  metric to light up the CEFR dashboard panel; move the process-local product metrics
  (`active_users`/`signups_total`) + rate-limiter + discover-cache to a shared store when scaling past
  one Cloud Run instance; revisit the `opentelemetry.sdk._logs.LoggingHandler` deprecation when the
  OTel logs signal stabilizes; confirm the exact `http_server_duration*` metric name in Grafana at
  deploy (the drift test tolerates suffixed/unsuffixed).

---

## Phase-5 / Phase-6 remaining (pointer)

Both phases are **as-code complete and CI-green**; only their **live halves** remain, and they are
owner-run against live cloud resources:

- **Phase 6** — the M4 staging leg is live and validated (see CHANGELOG). Remaining: the **prod
  cutover** (item A) + the live rollback drill + the live staging DB verifies (`6.2.4` RLS pytest
  against the staging DB, `6.2.5` confirm idempotent seed, `6.8.2` run `infra/deploy/rollback.sh`
  once) + `6.4.4` live secret-rotation + `6.8.4` backup/restore drill. Step-by-step:
  [`go-live-activation.md`](go-live-activation.md) §F.
- **Phase 5** — item B. Every exporter, dashboard, alert rule, and uptime descriptor is committed;
  lighting them up needs live Grafana/Sentry/PostHog creds against the deployed service.
  Step-by-step: [`go-live-activation.md`](go-live-activation.md) §G.
