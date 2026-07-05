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
  Real GDPR privacy policy (replace the `docs/privacy-policy.md` stub) + right-to-erasure text
  (unblocked by #91) + a deletion form; Apple/Play data-safety declarations, content ratings,
  listings, closed tests.
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
  support tooling (support views, abuse review, manual budget override); accessibility pass
  (screen-reader labels, contrast, font scaling). **Watch:** confirm Supabase free-tier idle-pausing
  / project limits at setup.

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
- **Coverage carve-outs.** `lengua_core/{models,prompts}.py`, `app/settings.py`, the whole
  `legacy_streamlit/`, and the web `src/main.tsx` + `src/components/ui/**` are excluded from the 80%
  gate; ~20 backend modules are `@pytest.mark.integration` (auto-skip offline), so the 80% gate is
  only truly enforced in CI with Postgres up. A local run without a reachable DB now auto-relaxes
  `--cov-fail-under` to 0 with a loud banner (`tests/conftest.py::pytest_configure`) instead of
  false-failing red — so local coverage still ≠ CI coverage, but a DB-less run is no longer a false red.
- **Base-image digest pin needs periodic refresh** (`apps/api/Dockerfile`) — bump the `python:3.12-slim`
  digest during deploy hardening or via Dependabot once enabled.
- **Test nits:** export-under-real-RLS assertion + a deleted-but-unexpired-token behavior test; the
  RLS migration drift test hardcodes predicate strings instead of parsing the canonical SQL.
- **Doc stubs:** `docs/privacy-policy.md` is a Phase 0 stub (`> Placeholder.`), replaced by the real
  GDPR policy in Phase 8 (item (D)); the runbook's **On-call** + **Store-release** sections are
  finalized at launch (Phase 9).
- **Stale code-comment doc citations.** A few source comments still cite planning design docs deleted
  in #115/#116 — `03-backend.md` (`app/quota.py`, `app/repositories/__init__.py`),
  `08-open-questions-and-costs.md` (`lengua_core/llm/keys.py`), `09-testing-quality.md`
  (`.github/workflows/ci.yml`), and `staging-validation*` (`e2e-staging/signup.spec.ts`, migration
  `0006`). Non-user-facing and build-safe; repoint to `CHANGELOG.md` when each area is next touched.
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
