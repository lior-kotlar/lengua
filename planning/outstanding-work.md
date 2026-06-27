# Outstanding work — running log

**What this is:** the single live log of everything in Lengua that is **not complete** — open
task boxes, code stubs/placeholders, coverage holes, owner-blocked items, paused PRs, and doc
inconsistencies. Whenever something incomplete is noticed (in any session), it gets appended here
with *where* + *status* + *date noticed*. Tick/strike items as they land.

This **complements** — does not replace:
- [`tasks/task-tracker.md`](tasks/task-tracker.md) — the structured phase rollup (source of truth for phase status).
- [`tasks/phase-N-*.md`](tasks) — the granular `- [ ]` task boxes (source of truth for individual tasks).
- [`owner-deferred-tasks.md`](owner-deferred-tasks.md) — owner-only repo-hardening actions (cross-linked, not duplicated).

> Seeded 2026-06-26 from a full-repo incompleteness sweep (336 open task boxes across 9 phase
> files + a code/test/docs scan). Conventions: ☐ = open, ☑ = done, 🔒 = blocked-on-owner,
> ⏸ = paused-for-review, 🛠 = in active build.

---

## 1. Active phase — Phase 2 (Auth & multi-tenancy) · 🛠 in progress

Driven by workflow `wf_9f3d03f7-0e5` (sequential per-group PRs). 2.3 done; 24 task boxes + 8
exit-gate items still open. See [`tasks/phase-2-auth-multitenancy.md`](tasks/phase-2-auth-multitenancy.md).

| | Item | Where | Status | Noticed |
|---|---|---|---|---|
| ☑ | **2.3** Backend JWT verify → `current_user` (+ reject expired/forged/`alg:none` + CORS) | phase-2 §2.3 | merged | 2026-06-26 |
| ☑ | **2.4** Per-user scoping — repos/routers already scoped (1.3b+2.3); added proving tests + `/me` profile+proficiency expansion | phase-2 §2.4 | merged PR #25 | 2026-06-26 |
| ☑ | **2.5** Profiles-on-first-login trigger (Alembic 0002), no-guest, demo/reviewer seed (login → ≥1 due card) | phase-2 §2.5 | merged PR #26 | 2026-06-26 |
| ☑ | **2.1** Email/pw + confirmation + 13-entry redirect allow-list; **2.2.3** branded templates; OAuth scaffolded+flagged | phase-2 §2.1, §2.2.3 | merged PR #27 | 2026-06-26 |
| ☑ | **2.6** RLS policies (Alembic 0003) + **per-request `authenticated`-role/JWT-claim session enforcement** (single choke point in `get_db`) + DB cross-tenant + RLS-coverage regression; reviewed (3-lens) + hardened (real-RLS write round-trip proves `authenticated` grants) | phase-2 §2.6 | merged PR #28 | 2026-06-26 |
| ☑ | **2.7** Historical SQLite import (`apps/api/data/lengua.db` → multi-tenant Postgres; idempotent + `--dry-run`) | phase-2 §2.7 | merged PR #29 | 2026-06-26 |
| ☑ | **2.8** Account export + cascade + **delete (service-role hard-delete, proven in CI)** + authz; reviewed (3-lens, all merge) + hardened (explicit `should_soft_delete:false`, `SecretStr` key, double-DELETE idempotency test, runbook caveat) | phase-2 §2.8 | merged PR #30 | 2026-06-26 |

**→ Phase 2 buildable work COMPLETE.** Remaining = owner-only: 2.2.1/2.2.2 (Resend SMTP + SPF/DKIM/DMARC) and 2.1.2/2.1.3 (Google/Apple OAuth creds, Apple needs the paid Developer acct).
| 🔒 | **2.2.1 / 2.2.2** Live Resend custom-SMTP delivery in both Supabase projects + SPF/DKIM/DMARC DNS | phase-2 §2.2 | owner (Kotlar) — needs real email/DNS | 2026-06-26 |
| 🔒 | **2.1.2** Google OAuth client id/secret + consent screen | phase-2 §2.1.2 | owner — real secrets (config scaffolded) | 2026-06-26 |
| 🔒 | **2.1.3** Apple OAuth (Service ID/Key ID/Team ID/.p8) | phase-2 §2.1.3 | owner — needs paid Apple Developer acct (Phase 7) | 2026-06-26 |

---

## 2. Owner-blocked / deferred (Kotlar — Ben lacks admin / paid accounts) · 🔒

Full detail + `gh` commands in [`owner-deferred-tasks.md`](owner-deferred-tasks.md). Non-blocking
for current code work.

| | Item | Task | When | Verify |
|---|---|---|---|---|
| 🔒 | Branch protection on `main` (would break autonomous self-merge if enabled now) | 0.6.3 | at launch | `gh api .../branches/main/protection` ≠ 404 |
| 🔒 | Dependabot alerts + security-update PRs | 0.6.4 | at launch | `gh api .../vulnerability-alerts -i` → 204 |
| 🔒 | CI secrets `GCP_REGION=europe-west1` + `SENTRY_ORG=kotlar-y7` | 0.7.7 | before Phase 5/6 | `gh secret list` shows both |
| 🔒 | Resend custom SMTP delivering in both Supabase projects (+ SPF/DKIM/DMARC) | 0.7.8 / 2.2.1 / 2.2.2 | before Phase 2 auth ships | real inbox delivery + 250 accept |
| 🔒 | Apple Developer Program ($99/yr) → invite Ben Admin + share `.p8` | Phase 7 (7.1) | Phase 7 (start early; verification slow) | enrolled; `com.lengua.app` bundle reserved |
| 🔒 | Google Play Console ($25 one-time) → invite Ben Release Manager | Phase 7 (7.1) | Phase 7 | account created |
| 🔒 | (optional) custom branded domain (~$10/yr) — v1 uses free subdomains | backlog | optional/later | — |

*Already resolved (for the record, not outstanding): 0.7.9 Vercel access (Ben is the free-tier
manager); 0.7.10 Grafana Cloud + Sentry (Ben joined both).*

---

## 3. Code-level stubs / placeholders / built-ahead-of-feature · ☐

Found by the repo scan — real deliverables that are intentionally stubbed pending a later phase.

| | Item | Where | Lands in |
|---|---|---|---|
| ☐ | `docs/privacy-policy.md` is a Phase 0 stub; real GDPR policy + "to be completed" section unwritten | docs/privacy-policy.md:3,35 | Phase 8 |
| ☐ | `docs/runbook.md` stub — **Health checks / Deploy-rollback / On-call** sections are empty TODOs | docs/runbook.md:9,14,19 | Phase 5/6/9 |
| ☐ | `docs/README.md` and `infra/README.md` end with bare `> Placeholder.` | docs/README.md:7; infra/README.md:10 | as docs fill in |
| ◐ | ~~Entire `apps/web/src` is the Phase 0 scaffold — `Home.tsx` renders only "Web shell scaffold"~~ — **4.1 landed the real app shell** (theming/routing/server-state/Supabase + shadcn primitives; `Home.tsx` replaced by `AppLayout` + per-screen stubs). Screens themselves are still stubs filled by 4.2–4.11. | apps/web/src/App.tsx; apps/web/src/components/ | Phase 4 (4.2–4.11) |
| ☐ | `app/main.py` docstring ("routers/auth/quota/OTel … later Phase 1 tasks") now partly **stale** — routers wired, quota still pending | apps/api/app/main.py:4 | tidy + Phase 3 |
| ☐ | `llm_usage` table + `settings` limit fields exist but the **Phase 3 cost-guard/quota gate that consumes them is not built** | app/db/models.py:152; app/schemas/settings.py:4 | Phase 3 |
| ☐ | `reviews.py` notes pending Phase 2 RLS filtering; `seed_dev_user.py` `current_user` is still the placeholder dev UUID | app/repositories/reviews.py:4; scripts/seed_dev_user.py:4 | Phase 2 (2.4/2.6) |

---

## 4. Coverage holes — product code not measured by the 80% gate · ☐

No disabled/xfail tests exist (clean). But these are real product modules that contribute nothing
to the coverage bar — revisit when each area is actively worked:

| | Excluded product code | Where | Note |
|---|---|---|---|
| ☐ | `lengua_core/models.py`, `lengua_core/prompts.py` (and legacy `gemini.py`) absent from coverage `source` allow-list | apps/api/pyproject.toml:134 | shared product code, never counted |
| ☐ | Whole `legacy_streamlit/` out of coverage + ruff + mypy | pyproject.toml:134,59,96 | deliberate legacy carve-out |
| ☐ | `app/settings.py` omitted ("boilerplate") | pyproject.toml:149 | borderline config-vs-product |
| ☐ | Frontend excludes `src/main.tsx` (bootstrap) + `src/components/ui/**` (shadcn) | apps/web/vite.config.ts:26 | bootstrap is real product code |
| ⚠ | ~20 API/repo/service/db test modules are `@pytest.mark.integration` → **auto-skip offline**; the 80% gate is only truly met in CI with Postgres up (local/offline `pytest` exercises none of those HTTP/repo/service paths) | apps/api/tests/conftest.py:120,123 | legitimate, but know that local coverage ≠ CI coverage |

---

## 5. Future-phase backlog (not started) · ☐

The bulk lives in the phase files; tracked here as a single pointer with live open-box counts
(task boxes + exit-gate boxes) from the 2026-06-26 sweep. **336 open boxes total.**

| Phase | Open | Notes |
|------:|:----:|---|
| 0 | 6 | all owner-deferred/non-blocking (§2 above); impl complete |
| 1 | 0 | ✅ done |
| 2 | 32 | 🛠 in progress (§1) |
| 3 — LLM quota & cost guard | 0 | ✅ done (M2) — usage counters, per-user caps, rate limit, global kill-switch, abuse guard, concurrency cap, BYOK seam, observability spans/metrics, zero-paid-usage load test |
| 4 — React web app | 0 | ✅ DONE (M3) — **all 44 task boxes + all 7 exit-gate boxes ticked**; React app at full parity with Streamlit ([`docs/streamlit-parity.md`](../docs/streamlit-parity.md)). The exit gate closed in the milestone PR by adding the dedicated end-to-end [`e2e/full-loop.spec.ts`](../../apps/web/e2e/full-loop.spec.ts) (login → generate → save → review reveal+grade → discover, zero real LLM calls); auth (incl. Google + Apple buttons) / RTL / 429+consent are proven by their group specs; the typed-client drift check runs every CI run incl. the merge commit. |
| 5 — Observability | 39 | OTel, custom spans/metrics, correlated logs, Sentry, Grafana dashboards, alerts, uptime, PostHog |
| 6 — Infra & CI/CD | 56 | Cloud Run, 2 Supabase + 2 Vercel envs, secrets, CD staging→gated-prod, rollback, flags, domains/CORS |
| 7 — Mobile (Capacitor) | 58 | paid store accts, signing, native projects/plugins, OAuth-in-webview, iOS/Android builds, OTA, device validation |
| 8 — Compliance & store | 36 | privacy/support URLs, GDPR rights, deletion form, Apple/Play data-safety, ratings, listings, closed tests |
| 9 — Launch | 23 | prod smoke all platforms, store submit/promote, domain cutover, 48h watch |

> Note: `task-tracker.md`'s summary table counts only *task* boxes (no exit-gate rows) and predates
> some splits, so its per-phase totals differ from the live open-box counts above.

---

## 6. Doc cleanups to make (low severity) · ☐

| | Fix | Where |
|---|---|---|
| ☐ | Exit-gate bullet lists "outstanding owner items (0.6.3, 0.6.4, **0.7.7–0.7.10**)" but 0.7.9/0.7.10 are already done — narrow the range to **0.7.7–0.7.8** | planning/tasks/phase-0-foundations.md:174 |
| ☐ | Refresh `app/main.py` module docstring (routers are now wired; only quota/Phase 3 remains) | apps/api/app/main.py:4 |
| ⚠ | **Operational caveat (from 2.6.2):** the API now assumes the `authenticated` role per request, so its runtime `DATABASE_URL` MUST be a Supabase-provisioned Postgres (has the `authenticated` role + `auth.uid()`). A bare Alembic-only Postgres would 500 on the role switch. Carry into Phase 6 deploy config. | apps/api/app/db/rls.py |
| ☐ | Untracked file `study-flow.html` at repo root (pre-existing, not created this session) — owner decide: commit, `.gitignore`, or delete | repo root |
| ☐ | `planning/outstanding-work.md` itself is untracked — fold into a docs PR so it's durable (agents keep flagging it as a stray file) | planning/outstanding-work.md |

*(Verified NOT a conflict: the suspected GCP_REGION/SENTRY_ORG status mismatch — task-tracker.md,
phase-0-foundations.md, owner-deferred-tasks.md, and MEMORY all agree those two secrets are still open.)*

---

## 7. RLS review follow-ups (PR #28, group 2.6) · from the 2026-06-26 adversarial review

3-lens adversarial review verdict: **design correct, tenant isolation genuinely proven & enforced
in CI** (all 3 lenses high-confidence; no critical/high issues). Items to close:

| | Item | Severity | Where |
|---|---|---|---|
| ☑ | ~~**Real `authenticated`-role write path proven only for `/languages`**~~ — CLOSED in the PR #28 hardening: added an un-overridden write round-trip (generate→save, review-grade, proficiency/settings) + explicit `has_table_privilege('authenticated', …)`/sequence assertions; went green → grants proven. | medium | apps/api/tests/test_rls_session.py (resolved) |
| ☑ | ~~**Phase 3 / `llm_budget` privilege**~~ — CLOSED in group 3.1 (PR #31, pre-merge) + the 3-lens hardening: `llm_budget` is `REVOKE`d from `authenticated`/`anon` **and** under deny-by-default RLS; `llm_usage` writes (INSERT/UPDATE/DELETE) are also revoked (SELECT kept for the RLS-scoped count read) so a user can't reset their own cap; both SECURITY DEFINER functions schema-qualify their tables and are `EXECUTE`-granted to `service_role` ONLY; the backend reaches them via a **dedicated** privileged `app.deps.get_usage_db` session (its own connection, never the RLS-bound `get_db`). Proven by `tests/test_rls.py`, `tests/db/test_role_privileges.py` (Alembic-side lockstep), `tests/test_usage_deps.py` (distinct sessions). | high (Phase 3) | migration 0004; supabase/migrations/20260626120000_llm_killswitch.sql |
| ◐ | **Stronger compile-time session-type split deferred (review item E).** `get_usage_db` yields a `UsageSession` newtype (marks the privileged boundary), but `UsageRepository` still takes a plain `AsyncSession` — required so `get_user_daily_count` can also be served by the RLS request session (must-fix B keeps `authenticated` SELECT for exactly that). A full guard (distinct request-vs-usage session types across *all* repos, so a per-user repo can't accept the RLS-off session) is a larger refactor left for later; the boundary docstrings on `get_usage_db`/`UsageRepository` carry the rule meanwhile. | nit | apps/api/app/deps.py; app/repositories/usage.py |
| ⚠ | **Prod transaction-pooler caveat:** asyncpg's prepared-statement cache breaks against Supabase's transaction pooler (6543) unless `statement_cache_size=0` / session pooler. RLS itself is pooler-safe (SET LOCAL re-applied per txn). Confirm prod `DATABASE_URL` **before Phase 6 deploy**. | medium (Phase 6) | apps/api/app/db/session.py:50 |
| ☐ | Migration drift test hardcodes predicate strings instead of parsing the canonical SQL — the "byte-for-byte match" isn't self-checking. | nit | apps/api/tests/db/test_rls_migration.py |
| ☑ | ~~Latent footgun: a session obtained **not** via `app.deps.get_db` bypasses RLS~~ — the one such surface (group 3.1's `get_usage_db`) now carries an explicit ⚠ BOUNDARY docstring + the `UsageSession` newtype marker; revisit if more privileged sessions appear. | nit | apps/api/app/db/rls.py; app/deps.py |

---

## 8. Account-lifecycle review follow-ups (PR #30, group 2.8) · from the 2026-06-26 adversarial review

3-lens adversarial review: **all three lenses → merge, high confidence**; CI green (CLEAN); no
blocking issues (no orphans, hard-delete proven in CI, secrets safe, authz structural). Defense-in-depth nits:

| | Item | Severity | Where |
|---|---|---|---|
| ☑ | ~~Make hard-delete explicit~~ — DONE in #30 hardening: `client.request("DELETE", …, json={"should_soft_delete": False})`; live test still proves hard delete. | nit | apps/api/app/services/account.py |
| ☑ | ~~`SecretStr` for the service-role key~~ — DONE in #30 hardening (read via `.get_secret_value()`). | nit | apps/api/app/settings.py |
| ☑ | ~~Soften "all your data" export wording~~ — DONE in #30 hardening (notes it omits `llm_usage` + email). | nit | app/schemas/account.py |
| ☐ | No boot/readiness check that `SUPABASE_SERVICE_ROLE_KEY` is set → account-deletion (a store-compliance requirement) is silently broken in a misconfigured prod until first exercised. | nit (ops) | app/services/account.py |
| ☑ | ~~Runbook cascade-invariant note~~ — DONE in #30 hardening. | nit (doc) | docs/runbook.md |
| ◐ | Double-DELETE idempotency test DONE; still open: export-under-real-RLS assertion + a deleted-but-unexpired-token behavior test. | nit (tests) | apps/api/tests/test_account_*.py |

---

## 9. Phase 3 (LLM quota & cost guard) — ✅ COMPLETE (M2 reached) · owner-confirmation items remain

**✅ Phase 3 is COMPLETE — M2 reached (multi-user with the LLM cost guard armed).** All 8 groups
(3.1–3.9) + the 8 exit-gate boxes are merged green; the per-PR quality gate held throughout (446
backend tests, 100% line+branch, mypy --strict, ruff). The headline **zero-paid-usage load test**
(`tests/integration/test_load_cost_guard.py`) proves caps/limits/budget hold under sustained
concurrent multi-user traffic with `FakeLLM` (zero real LLM calls) and `FakeLLM.call_count ==
GLOBAL_DAILY_BUDGET` (the operator key can never be billed past the budget). **Every default below is
IMPLEMENTED-with-a-default** and env-overridable; the items still marked OPEN are owner *confirmation*
calls (nothing is blocked):

- ☐ **OPEN (owner):** confirm `GLOBAL_DAILY_BUDGET` (default 1000) + the per-user caps
  (`MAX_*_PER_DAY` / `DEFAULT_*_PER_DAY`) against the **real Groq `llama-3.1-8b-instant` free-tier
  requests/day** so the ceiling is set from a real number (the defaults are conservative placeholders
  « any plausible free RPD; note RPD ÷ retry attempts (3) bounds worst-case fan-out).
- ☐ **OPEN (Phase 6):** swap the **in-process** rate limiter (`app/ratelimit.py`) and the
  **in-process** `/discover` reuse cache (`app/discover_cache.py`) for a distributed backend
  (Postgres/Upstash) behind their existing Protocol seams when Cloud Run scales >1 instance — until
  then in-process under-counts/misses across replicas (never over-spends).
- ☐ **OPEN (Phase 6 DEPLOY CONSTRAINT):** **run a single API instance** until the distributed rate
  limiter lands — the global kill-switch + per-process concurrency cap (3.5, `LLM_MAX_CONCURRENCY`)
  bound overshoot per process, but the per-user rate limiter under-counts across instances.

🛠 **3.8 landed + Phase 3 EXIT GATE closed (observability spans/metrics + the load test).** New
`app/llm_observability.py` owns the LLM span tracer + a no-op-unless-configured `MeterProvider`
(mirrors the tracer's zero-egress discipline) with the cost-guard instruments (`llm_calls_total
{kind,result}`, `llm_cap_hits_total{gate}`, `llm_budget_remaining` ObservableGauge). `QuotaGuard`
starts the `llm.call` span in `check()` (sets `quota.kind`/`quota.cap_hit`/`budget.remaining` + the
blocked/success/error metrics), and the new `app/llm_runner.py` `run_provider(...)` boundary sets the
`llm.*` attrs (provider/model/latency/tokens). Vendor token usage is threaded out through a core seam
(`lengua_core/llm/usage.py` `capture_usage`/`report_usage`; Groq/Gemini report real tokens via a
contextvar-held mutable sink that survives the `to_thread` hop; `FakeLLM` reports deterministic stubs
+ `FakeLLM.call_count` is now lock-guarded for atomic counting under the concurrency cap). `quota_guard`
became a **generator dependency** so the span is always finalized (even on a provider error after the
gate admits). Path reconciled: tests live in `tests/obs/` (the task said `tests/observability/`). The
load test (`tests/integration/test_load_cost_guard.py`) drives genuinely concurrent committed-session
traffic for the kill-switch (resets the persistent `llm_budget[today]` row on setup/teardown, sizes
the budget for the accumulated count, and waves are sized so no request races the boundary → exact
`call_count`) + rolled-back bursts for the per-user cap / rate limit + a DB-free `run_provider`
concurrency-cap check. `openapi.json` unchanged (spans/metrics are internal).

_(Original autonomous-defaults note, retained for history:)_ Phase 3 was driven autonomously (owner
asked to complete it without pausing) with safe, conservative defaults; **confirm/adjust the OPEN
items above later:**

**Progress:** 🛠 **3.1 landed (PR #31, merging after the review's must-fixes)** — usage accounting +
the server-only kill-switch privilege model (Alembic `0004` + canonical `20260626120000_llm_killswitch.sql`,
`UsageRepository`, privileged `get_usage_db`). The 3-lens cost-guard review approved-with-fixes; all
folded into PR #31: (A) `get_usage_db` now opens its **own** dedicated session (was sharing the
RLS-bound request session → would have run the RPCs as `authenticated`); (B) `llm_usage` writes
`REVOKE`d from `authenticated`/`anon` so a user can't reset their own cap (SELECT kept); (C)
deny-by-default RLS on `llm_budget` as a second lock; (D) schema-qualified definer bodies; (E)
`UsageSession` newtype marks the privileged boundary (full repo-type split deferred — see §7); (F1)
Alembic-side role-privilege lockstep test; (F2) `anon` denial assertions; (G) runbook + docstrings
("never downgrade past 0004 in prod").

🛠 **3.2 landed (per-user daily caps)** — typed quota config in `app/settings.py` (`MAX_GENERATE/DISCOVER/EXPLAIN_PER_DAY`
= 50/30/100, `DEFAULT_*_PER_DAY` = 20/10/50; env-overridable; documented in `.env.example` under
`# ── LLM cost guard (Phase 3) ──`). New `app/quota.py` (the single gate-chain chokepoint, with a module
docstring laying out the documented order **email-verified→rate-limit→daily-cap→global-budget** + extension
points so 3.3/3.4 slot in cleanly): `resolve_user_cap(user_id, kind)` reads the per-user `user_settings`
override (`daily_cap_generate`/`daily_cap_discover`/`daily_cap_explain`) and clamps it with `min()` to the
server max (missing/blank/non-numeric → server default); `enforce_daily_cap`/`QuotaGuard.check` compares
today-UTC's `get_user_daily_count` to the cap and raises `DailyCapReached` → **429** with the exact body
`{"code":"daily_cap_reached","kind":...}` (app-level exception handler). One shared `QuotaGuard` is wired into
every LLM endpoint: `/generate`, `/discover`, `/discover/accept` via the `quota_guard(kind)` FastAPI dependency
(accept counted as `generate`); **`/explain` cache-aware deviation** — the guard is built `enforce=False` and the
same gate runs inside `ExplainService` *after* the cache lookup, so a cache hit is free (no gate/increment) and only
a cache miss is gated+counted. On success, `QuotaGuard.record_success` increments via
`UsageRepository.increment_usage(current_user.id, kind, today)` on the privileged `get_usage_db` session (always the
JWT-derived id; the global `llm_budget` counter now begins accumulating, but its kill-switch GATE is still 3.4).
Tests: `tests/test_config.py::test_quota_ceilings_load`, `tests/quota/test_caps.py`,
`tests/api/test_quota_endpoints.py::test_each_kind_capped`, `tests/services/test_explain_service.py`. Backend gate
green (388 tests, 100% line+branch; `app/quota.py` 100%). Test-infra note: api tests override `get_usage_db` onto the
rolled-back `db_session` (hermetic, no committed counter pollution); `tests/test_rls_session.py`'s real-`get_db`
loop now also overrides `get_usage_db` onto its loop-local engine (so the newly-gated `/generate` doesn't leak a
process-wide-engine connection across event loops). 3.3–3.9 not started.

🛠 **3.3 + 3.7 landed (per-user rate limit + email-verified gate + signup-abuse guard)** — new
`app/ratelimit.py`: a `RateLimiter` Protocol + an in-process sliding-window-log `InProcessRateLimiter`
with an **injectable clock** (default `time.monotonic`), via the process-wide-singleton
`get_rate_limiter()` dependency. **Locked decision implemented: in-process, NO slowapi** (heavier,
harder to fake the clock); the module docstring + this log flag the **Phase-6 distributed
(Postgres/Upstash) swap** (Cloud Run >1 instance → in-process under-counts). `QuotaGuard.check` now
runs the FULL documented chain **email-verified → rate-limit → daily-cap (→ global-budget slot)**:
3.7.1 email gate (`CurrentUser.email_verified` false → **403** `{"code":"email_unverified"}`, zero
provider calls, FIRST gate); 3.3.2 rate gate (over `RATE_LIMIT_PER_MIN`=10 → **429**
`{"code":"rate_limited"}` + `Retry-After`; keyed by `user_id`, counts ALL gated kinds; token consumed
once past email even if the cap then blocks); 3.3.3 ordering proven by `test_gate_order.py` (relax the
gates one at a time → 403→429 rate→429 cap). 3.7.2 day-0 clamp in `enforce_daily_cap`: a day-0 account
(its `profiles.created_at` is today-UTC, read via `ProfilesRepository`) gets effective generate cap =
`min(resolved, NEW_ACCOUNT_DAY0_GENERATE_CAP=5)`; established accounts unaffected; CAPTCHA slot is a
code comment only (not built). `RATE_LIMIT_PER_MIN` + `NEW_ACCOUNT_DAY0_GENERATE_CAP` documented in
`.env.example`; README updated; routers + `openapi.json` unchanged (gates = app-level exceptions + a
dependency, no schema delta). Tests: `tests/quota/{test_eligibility,test_ratelimit,test_gate_order,test_abuse_guard}.py`
(+ a `test_config` rate/day-0 load test); api fixtures override `get_rate_limiter` with a fresh
per-test limiter for isolation. Backend gate green (396 tests, **100.00%** line+branch cov;
`app/quota.py` + `app/ratelimit.py` both 100%).

🛠 **3.4 landed (global daily budget kill-switch) — ⏸ PR OPEN, awaiting orchestrator 3-lens review +
merge (cost-critical; not self-merged).** Config `GLOBAL_DAILY_BUDGET` (default **1000**, env-overridable,
documented in `.env.example` as "set BELOW the active provider's free RPD"; Groq `llama-3.1-8b-instant`
free tier ≈ a few thousand/day). The **LAST** gate in `QuotaGuard.check` (after the per-user daily cap):
it reads the GLOBAL `llm_budget` counter on the **privileged** `get_usage_db`/`UsageSession` (the
`authenticated` role is REVOKE'd from `llm_budget` and can't EXECUTE the reader, so the read MUST be on
the privileged session — never the RLS `get_db`) and, once the day's count `>= GLOBAL_DAILY_BUDGET`,
refuses **every** caller with **429** `{"code":"daily_limit_reached","message":"Daily limit reached,
please try again tomorrow."}` (`GlobalBudgetReached` → app-level handler; `DAILY_LIMIT_MESSAGE` constant
shared by handler + tests). **Status 429** chosen — 03-backend.md lists "503/429" without mandating 503,
so 429 keeps the kill-switch consistent with `rate_limited`/`daily_cap_reached`. Increment is
**check-then-increment-on-success** (unchanged from 3.2): `record_success` runs only after the provider
returns, atomically bumping both `llm_usage`+`llm_budget`; failed/blocked/cache-hit calls burn no budget;
the bounded overshoot under concurrency (read-before-call, increment-after-success) is documented at the
gate (bounded by `LLM_MAX_CONCURRENCY` from 3.5; no refund/decrement path — a refund would let a failed
call un-spend budget). Applies to all three gated kinds (generate/discover/explain-on-cache-miss); a
cache hit never consults the budget. Tests: `tests/quota/test_budget.py`
(`test_kill_switch_trips` over real HTTP + at the gate, `test_failed_call_no_increment`),
`tests/integration/test_global_killswitch.py` (NEW `tests/integration/` dir — drives real HTTP `/generate`
as user A until the ceiling, then proves a DIFFERENT user B is refused too → budget is GLOBAL not
per-user, FakeLLM only, `call_count == BUDGET` so blocked calls make zero provider calls),
`tests/test_config.py::test_global_budget_loads`. Backend gate green (initially 400 tests, 100.00%
line+branch; `app/quota.py` 100%); ruff+mypy --strict clean; `openapi.json` unchanged (gate = app-level
exception, no schema delta). 3.5–3.6, 3.8–3.9 not started.

**Post-review hardening (folded into the SAME PR #34 after the 3-lens review → all MERGE):** (1) closed
the `/discover/accept` billed-but-uncounted window — `accept` = generate (billed provider call) → save
(persist); the spend is now counted **right after the provider call and BEFORE `save`** (the `guard` is
threaded into `DiscoverService.accept`, mirroring `ExplainService`), so a `save` failure still counts the
billed call (safe direction; cards roll back) instead of skipping the increment. `/generate` has no such
window (no persist); `/explain` already counted before its persist loop. Regression test
`test_discover_accept_counts_billed_call_even_if_save_fails` monkeypatches `GenerateService.save` to raise
after a successful provider call and asserts BOTH `llm_budget` + `llm_usage` still bumped by 1 (and the
`discover` counter stayed 0 — accept meters as `generate`). (2) the request's UTC `day` is now computed
**once** in `QuotaGuard.check` and threaded into the daily-cap read, the budget read, AND
`record_success`'s increment (stored on `self._day`), so a request straddling 00:00 UTC can't read day N
then increment day N+1; `enforce_daily_cap`/`_account_created_today` take an optional `day`. (3) doc-only:
the `GLOBAL_DAILY_BUDGET` comments (`.env.example` + `app/settings.py`) now say "set below provider RPD **÷
max retry attempts (3)**" — `call_with_retry` does up to `DEFAULT_MAX_ATTEMPTS=3` real HTTP requests per
counted call, so RPD/3 bounds the worst-case fan-out (default 1000 → ≤3000 requests, still under Groq's
free RrPD with margin). NOTE: closing (1) required a `TYPE_CHECKING`-only import of `QuotaGuard` in
`app/services/discover.py` — a runtime import forms a cycle (`app.quota` → `app.deps` →
`app.services.account` → `app.services.__init__` → `app.services.discover`), since `DiscoverService` (unlike
`ExplainService`) is eagerly imported by the services package `__init__`.

🛠 **3.5 + 3.9 landed (concurrency cap + backoff with jitter + BYOK key-resolution seam) — MERGE
MODE (resilience/seam, low-risk).** New `app/llm_runner.py`: a process-global `asyncio.Semaphore`
sized by `LLM_MAX_CONCURRENCY` (default 4, documented in `.env.example`) bounds in-flight provider
calls; since the provider methods are **sync/blocking**, `LLMConcurrencyLimiter.run` offloads each to
a worker thread (`asyncio.to_thread`) UNDER the semaphore (event loop stays responsive AND calls are
genuinely concurrent so the cap is real), exposed via the `get_llm_limiter()` singleton dependency
(mirrors `get_rate_limiter`; overridable in tests, `reset_llm_limiter()` rebuilds) and threaded into
the Generate/Discover/Explain services + routers (default = singleton so the save-only `GenerateService`
needs no limiter). Over the cap a request waits briefly (bounded by `ACQUIRE_TIMEOUT_SECONDS=5`) then
`ProviderBusy` → **503** `{"code":"server_busy","message":"The server is busy, please try again in a
moment."}` (+ short `Retry-After`) — never an unbounded queue, never a 500. **3.5.2:**
`lengua_core/llm/retry.py` `call_with_retry` gains **full jitter** (injectable `rng`, delay =
`base_delay*2**(n-1)*rng()`; a faked `rng()`→1.0 reproduces the exact un-jittered backoff so tests
stay deterministic) and, when transient 429/5xx persist across every attempt, raises a clean typed
`LLMTransientError` (raw vendor error as `__cause__`) instead of re-raising the vendor exception — the
app maps it to the SAME friendly 503 `server_busy` via `register_llm_handlers` (so "LLM temporarily
unavailable" is one contract whether the cause is local saturation or a persistent upstream 429).
**3.9.1:** `resolve_llm_key(user)` in new `lengua_core/llm/keys.py` is now the SINGLE key chokepoint
— today always returns the operator env key for the active provider; the `user` param is the inert
future BYOK override. `GroqProvider.from_env`/`GeminiProvider.from_env` obtain the key ONLY through it;
a grep test (`tests/llm/test_key_resolution.py`) proves the key env-var names appear in exactly one
module (`keys.py`). **3.9.2 (DESIGN ONLY):** BYOK design note in `docs/byok-seam.md` + the `keys.py`
module docstring — references `resolve_llm_key` + `profiles.plan` (how a per-user key branches in the
resolver, and how the caps/rate-limit/global-budget gates would SKIP a BYOK user since they protect
the *operator* key). **No BYOK built**: no key storage, no UI, no new `profiles` columns, no
per-user branching. Tests: `tests/quota/test_concurrency.py` (cap high-water-mark ≤ 2, busy→503,
singleton/reset, 503 rendering), `tests/llm/test_backoff.py` (retries→`LLMTransientError`→503),
`tests/llm/test_key_resolution.py` (operator-key-only + grep), `tests/llm/test_retry.py` updated for
jitter + the typed-error-on-exhaustion. Backend gate green (416 tests, **100.00%** line+branch;
`app/llm_runner.py` + `lengua_core/llm/{keys,retry}.py` all 100%); ruff+mypy --strict clean;
`openapi.json`+`packages/api-types` regenerated (route-description deltas only — the 503 is an
app-level handler, no schema response delta). README "Usage & cost limits" extended (server-busy 503 +
transient backoff). 3.6 + 3.8 remain (cost minimization: word/token caps + explain/discover caching;
observability spans/metrics).

🛠 **3.6 landed (cost minimization — request/token caps + discover reuse) — MERGE MODE (low-risk
caches/validation).** (3.6.1) `/generate` request size is now capped by **Pydantic validation**:
`GenerateRequest.words` carries `max_length` = the new env-overridable `Settings.max_words_per_request`
(default reuses `lengua_core.llm.retry.MAX_WORDS_PER_REQUEST=30`), so an over-limit list is **rejected
422 at the API boundary** — a HARD reject, NOT silent truncation (`cap_words` stays a defensive
provider-side floor for any non-API caller). The constraint surfaces as `words.maxItems` in
`openapi.json`/`packages/api-types` (regenerated). The existing `GENERATE_MAX_TOKENS` output cap is
asserted to reach the vendor (Groq `max_tokens=` / Gemini `max_output_tokens=`) — made observable by
driving the real `GroqProvider` with a recording fake vendor client. (3.6.2) confirmed end-to-end that
an `/explain` cache hit is FREE — zero provider calls AND no `llm_usage` increment on a repeat — the
authoritative `test_explain_cache.py::test_cache_hit_skips_llm` (reconciled with the 1.5b persistence
test + the 3.2 cap test; adds the `llm_usage`-unchanged dimension neither asserted). (3.6.3, NEW) a
repeated `/discover` for the same `(user, language, topic, count)` within `DISCOVER_REUSE_WINDOW_SECONDS`
(new env setting, default **300**) reuses the prior preview from a new in-process TTL cache
(`app/discover_cache.py`: a `DiscoverCache` Protocol + `InProcessDiscoverCache` with an **injectable
clock** + bounded eviction (TTL + `MAX_ENTRIES=1024`, oldest-first), exposed via the process-wide
singleton `get_discover_cache()` / `reset_discover_cache()` — mirrors the rate-limiter seam). `/discover`
is now cache-aware exactly like `/explain`: the route hands in an UNCHECKED guard
(`quota_guard("discover", enforce=False)`) and `DiscoverService.suggest` runs `check`/`record_success`
**only on a cache miss**, so a reuse HIT makes no provider call and burns no gate/increment (the
language-ownership 404 check still runs first). New env vars documented in `.env.example` + README
"Usage & cost limits". Test-infra: the api/quota/multiuser fixtures override `get_discover_cache` with a
fresh frozen-clock cache (so the process-global cache never bleeds across tests/event loops, mirroring
`get_rate_limiter`/`get_llm_limiter`); `test_discover_service.py` passes a fresh cache; `test_quota_endpoints.py`'s
discover calls were varied by `topic` (an identical repeat is now FREE, so they'd otherwise stop counting).
Tests: `tests/api/{test_generate_limits,test_explain_cache,test_discover_reuse}.py`, `tests/quota/test_discover_cache.py`
(TTL expiry, copy-on-get/put, key scoping, bounded eviction + recency-refresh, singleton),
`test_config.py::test_cost_minimization_caps_load`. Backend gate green (429 tests, **100.00%** line+branch;
`app/discover_cache.py` + touched `services/discover.py`/`routers/discover.py`/`schemas/generate.py` all 100%);
ruff+mypy --strict clean; `openapi.json`+`packages/api-types` regenerated (`words.maxItems` + route-desc deltas).
**Phase-6 distributed-cache caveat (logged below + at the `app/discover_cache.py` seam + `.env.example`):**
the reuse cache is in-process, so a repeat landing on a *different* Cloud Run instance simply misses (makes
a fresh, fully-gated call — never wrong, just not reused); the distributed (Redis/Upstash or TTL Postgres)
swap is a Phase-6 task behind the same `DiscoverCache` Protocol — the same single-instance-now caveat family
as the in-process rate limiter. **3.8 (observability spans/metrics) remains.**

> **Carry-forward — discover-reuse cache is in-process (medium; Phase-6 DEPLOY CONSTRAINT).** The
> `/discover` short-window reuse cache (`app/discover_cache.py`, group 3.6.3) lives in this process's
> memory, so with >1 Cloud Run instance a repeated discover that lands on a different replica MISSES and
> makes a fresh (fully gated + counted) provider call — correct, just not reused (no over-spend, no wrong
> data). Swap `InProcessDiscoverCache` for a shared store (Redis/Upstash sliding window or a TTL Postgres
> table) behind the same `DiscoverCache` Protocol + `get_discover_cache()` dependency when scaling out —
> the call site (`DiscoverService.suggest`) doesn't change. Same single-instance-now seam family as the
> in-process rate limiter (3.3.1) and the kill-switch overshoot bound (3.5).

> **Lazy privileged-session acquisition — deferred (logged, not done).** The 3.2 review flagged that
> `quota_guard` resolves the privileged `get_usage_db` session eagerly (as a FastAPI sub-dependency) even
> on fast-fail paths (email/rate/cap-blocked, explain cache-hit) that never read the budget. Making it
> lazy was considered for this PR but **deferred**: every quota/api test fixture overrides `get_usage_db`
> to share the rolled-back `db_session`, so a clean lazy acquisition would require reworking the override
> seam (a session *factory* the tests re-override) across `tests/api/conftest.py`,
> `tests/quota/conftest.py`, and `multiuser_client` — a non-trivial change that risks correctness/clarity
> on the cost-critical kill-switch PR. Eager acquisition is correct and fully tested today; revisit as a
> follow-up (pairs naturally with the Phase-6 connection-pool/exit-gate load-test work and the §7
> session-type-split item). The bounded overshoot/pool pressure is acceptable because the budget sits far
> below the provider's free RPD.

> **Carry-forward — concurrency-cap sequencing (medium; Phase-6 DEPLOY CONSTRAINT).** The kill-switch is
> read-then-increment-on-success, so when the global budget crosses the ceiling a **bounded, one-shot**
> overshoot is possible = the number of in-flight gated requests at that instant. The hard bound on that is
> `LLM_MAX_CONCURRENCY` (the global asyncio semaphore) — **LANDED in group 3.5** (`app/llm_runner.py`,
> default 4). Per-process overshoot is now bounded; raising `GLOBAL_DAILY_BUDGET` near the provider RPD or
> running >1 instance still needs the distributed rate limiter below. Separately, the per-user rate limiter is
> **in-process** today, so it **under-counts across instances** (each replica keeps its own window) — the
> distributed (Postgres/Upstash) swap is a Phase-6 task (`app/ratelimit.py` seam). Until both land, run a
> single API instance. (Recorded here as a deploy constraint for Phase 6 / group 3.5.)

> **Carry-forward — exit-gate load test vs the persistent daily counter (advisory).** By design the global
> `llm_budget[day]` row **persists for the rest of the UTC day** once tripped (the kill-switch is meant to
> stay tripped). So whoever authors the **Phase-3 exit-gate load test** must account for accumulated state:
> run it on an **ephemeral DB**, OR reset/delete the day's `llm_budget` row before/after, OR size
> `GLOBAL_DAILY_BUDGET` for the already-accumulated count — otherwise a re-run starts with budget already
> spent (or part-spent) and the assertions skew. (Also true for any local re-run of
> `tests/integration/test_global_killswitch.py` against a non-rolled-back DB; the test itself runs on the
> rolled-back `db_session`, so it's clean.)

| | Question / decision | Default I'm using | Task |
|---|---|---|---|
| ◐ | **`GLOBAL_DAILY_BUDGET`** — project-wide daily LLM-call ceiling, "set below the active provider's free RPD". **IMPLEMENTED with default 1000** (env-overridable; documented in `.env.example` with a pointer to provider RPD; kill-switch gate + tests landed in 3.4). **Still wants owner confirmation of the real Groq `llama-3.1-8b-instant` free-tier requests/day** so the ceiling is set from a real number (the 1000 default is a deliberately conservative placeholder « any plausible free RPD). | a conservative value comfortably below Groq's free daily limit; documented in `.env.example` with a pointer to the provider RPD | 3.4.1 |
| ❓ | **Per-user daily caps + hard server maxima** (`MAX_GENERATE/DISCOVER/EXPLAIN_PER_DAY`) + defaults. | modest env-overridable defaults | 3.2.1 |
| ✅ | **`RATE_LIMIT_PER_MIN`** per user. | **IMPLEMENTED with default 10** (env-overridable; documented in `.env.example`). | 3.3.2 |
| ✅ | **Rate-limiter backend**: in-process vs Postgres/Upstash sliding-window. Cloud Run may scale >1 instance (Phase 6) → in-process under-counts. | **IMPLEMENTED in-process** (`InProcessRateLimiter`) behind a `RateLimiter` Protocol; **distributed multi-instance swap flagged for Phase 6** at the seam (`app/ratelimit.py` docstring). | 3.3.1 |
| ✅ | **Signup-abuse guard** — day-0 cap / cooldown value; where a captcha would slot in. | **IMPLEMENTED**: reduced first-day generate cap `NEW_ACCOUNT_DAY0_GENERATE_CAP=5` (env-overridable); captcha is a code comment only (not built). | 3.7.2 |
| ⚠ | **`llm_budget` must be server-only under RLS** (carried from §7): the backend connects as the `authenticated` role, so the global kill-switch counter needs a SECURITY DEFINER increment function owned by `postgres` + `REVOKE` from `authenticated`/`anon`, so users can't read or tamper with it while the atomic `llm_usage`+`llm_budget` bump still works. | SECURITY DEFINER increment fn + REVOKE | 3.1.2/3.1.3 |

### Finalized Phase-3 defaults (chosen 2026-06-26 — conservative; env-overridable; confirm/adjust later)

Driving Phase 3 autonomously with these safe defaults. All live in `app/settings.py` + `.env.example`.
The kill-switch (`GLOBAL_DAILY_BUDGET`) is the "never get a bill" backstop and is set far below any
plausible provider free-tier RPD. **Owner: confirm the GLOBAL_DAILY_BUDGET vs the real Groq
`llama-3.1-8b-instant` free-tier requests/day, and whether the per-user caps feel right.**

```
GLOBAL_DAILY_BUDGET=1000              # project-wide successful-LLM-call ceiling/day; « provider free RPD
MAX_GENERATE_PER_DAY=50               # hard server maxima per kind (user can't exceed even by raising own cap)
MAX_DISCOVER_PER_DAY=30
MAX_EXPLAIN_PER_DAY=100
DEFAULT_GENERATE_PER_DAY=20           # per-user default when user_settings has no override
DEFAULT_DISCOVER_PER_DAY=10
DEFAULT_EXPLAIN_PER_DAY=50
RATE_LIMIT_PER_MIN=10                 # per-user sliding-window requests/min across LLM kinds
LLM_MAX_CONCURRENCY=4                 # global in-flight provider-call semaphore
NEW_ACCOUNT_DAY0_GENERATE_CAP=5       # signup-abuse guard: reduced generate cap on the account's first day
MAX_WORDS_PER_REQUEST=30              # /generate word-list cap (also bounds prompt size)
DISCOVER_REUSE_WINDOW_SECONDS=300     # short in-process /discover preview reuse window
```

**Decisions locked for the build:**
- Rate limiter = **in-process** (`InProcessRateLimiter`) behind a `RateLimiter` Protocol with an injectable
  clock — NO new dependency (slowapi rejected: heavier, harder to fake the clock). **Distributed
  (Postgres/Upstash) swap flagged for Phase 6** (Cloud Run may scale >1 instance → in-process under-counts).
- Discover reuse + (future) distributed rate limit share the same "single-instance now, distributed in
  Phase 6" caveat — documented at each seam.
- `llm_budget` server-only via Alembic `0004` (+ canonical `supabase/migrations/20260626120000_llm_killswitch.sql`,
  kept in lockstep): SECURITY DEFINER `increment_llm_usage(uuid,text,date)` (atomic both-table row-locked bump,
  returns new budget count) + `get_llm_budget_count(date)` reader, owned by `postgres`, `REVOKE ALL ON llm_budget
  FROM authenticated, anon`. **`EXECUTE` granted to `service_role` ONLY — NOT `authenticated`** (corrected from
  the earlier draft): Supabase exposes a PostgREST RPC to `authenticated`, so granting it EXECUTE would let any
  logged-in user `POST /rest/v1/rpc/increment_llm_usage` and trip/hide the global kill-switch for everyone (DoS).
  The default `PUBLIC` EXECUTE is revoked too; the backend invokes both functions via the privileged server-only
  `app.deps.get_usage_db` session (the connecting `postgres` role keeps EXECUTE as owner). All role grants/revokes
  guarded by `to_regrole(...) IS NOT NULL` so the migration still round-trips on bare Postgres. **Landed in group 3.1.**
- Counters bump **only after a successful provider call** (check-then-increment); slight bounded overshoot
  under concurrency is acceptable because the budget is set well below the free RPD and `LLM_MAX_CONCURRENCY`
  bounds in-flight calls. Cache hits (explain hit / discover reuse) make no call and no increment.

---

## 10. Phase 4 (React web app) — ✅ DONE (M3 reached)

All 44 task boxes (4.1–4.11) merged green; the React web app is at full parity with the legacy
Streamlit app (see [`docs/streamlit-parity.md`](../docs/streamlit-parity.md)). **All 7 exit-gate
boxes are now ticked** — closed by the milestone PR, which added the dedicated end-to-end
[`e2e/full-loop.spec.ts`](../../apps/web/e2e/full-loop.spec.ts) (login → generate → save → review
reveal+grade → discover, through the real server seam, zero real LLM calls) so a SINGLE spec proves
the whole loop, and strengthened `e2e/auth.spec.ts` to assert **both** Google + Apple buttons
present + enabled. Auth-401/refresh-retry stays vitest-covered (4.3 decision); RTL / 429+consent are
proven by their group specs; the typed-client drift check (`pnpm gen:api` → no diff) runs on every
CI run including the merge commit.

**4.1 — App shell & foundations · DONE (PR for group 4.1).** Vite/React/TS scaffold extended into the
production shell: shadcn primitives, light/dark/system theming, react-router auth-vs-app route tree +
shared layouts, TanStack Query, and a lazy auth-only supabase-js client + fail-fast env validator.
Web gate green (35 vitest tests, 100% product coverage; lint/format/typecheck/build clean; env-less
Playwright home smoke updated + passing).

**4.2 — Typed API client · DONE.** Root `pnpm gen:api` convenience script (delegates to
`pnpm --filter api-types generate`) regenerates `packages/api-types/src/schema.ts` from
`apps/api/openapi.json` — no backend change, so the existing CI drift check stays clean. `apps/web`
now depends on the `api-types` workspace package (root `pnpm-lock.yaml` updated). New
`apps/web/src/lib/api-client.ts` is the single typed seam: a lazy authed singleton
(`getApiClient()`) whose request middleware injects `Authorization: Bearer <token>` from the
CURRENT Supabase session (read fresh per request, never cached, never logged), plus `unwrap()` →
typed data on 2xx / throws `ApiError {status,code,message,retryAfter,body}` parsed from body+headers
(the cost-guard contract; transport failures → status 0). `api-types/index.ts` re-exports the
`ApiClient`/`Middleware`/`ClientOptions` types so web imports only from `api-types` (no phantom
`openapi-fetch` dep). Web gate green (49 vitest tests, 100% product coverage incl. `api-client.ts`;
`pnpm gen:api` no-diff; frozen-lockfile install clean).

| | Item | Where | Status / decision | Noticed |
|---|---|---|---|---|
| ☑ | **4.2.1 / 4.2.2** root `pnpm gen:api` + drift check (already in CI) + typed authed `apiClient` (bearer-from-session middleware, `unwrap`, typed `ApiError` for the cost-guard states) | apps/web/src/lib/api-client.ts; package.json; packages/api-types/src/index.ts | merged | 2026-06-27 |
| ◐ | **Env fail-fast vs env-less CI build (decision).** 4.1.6's verify says `vite build` should "fail fast" on a missing `VITE_*` var, but Vite statically **inlines** build-time env and the CI build/E2E jobs build **without** these vars (the env-less home smoke must render). **Safe default chosen:** validate at config-load / first Supabase use via `readEnv()` (throws a clear error naming the missing var), proven by `apps/web/src/lib/env.test.ts` — NOT by failing `vite build`. Documented in `apps/web/.env.example` + the phase-4 doc. | apps/web/src/lib/env.ts; supabase.ts | decided (no owner action needed; flag if a literal build-time guard is later wanted) | 2026-06-27 |
| ☐ | **4.1 scope deferrals (by design):** ~~route gating / redirect-unauthenticated is NOT wired yet~~ (**landed in 4.3**); ~~the typed `apiClient` + `api-types` workspace dep land in **4.2**~~ (**landed in 4.2**). Authenticated screens are heading-only stubs until their groups (4.4–4.11). | apps/web/src/components/app-layout.tsx; pages/ | expected — later 4.x groups | 2026-06-27 |
| ☑ | ~~**CI E2E harness unchanged this group** (per 4.1 scope)~~ — **reworked in 4.3**: the `e2e` job now builds the web bundle wired to the ephemeral stack + runs Playwright auth specs (`E2E_STACK=1`) against the seeded demo account; the env-less `build`-job bundle stays for a11y/perf. | apps/web/e2e/auth.spec.ts; .github/workflows/ci.yml | done in 4.3 | 2026-06-27 |

**4.3 — Auth screens & session handling + E2E harness rework · DONE (the linchpin group).** Signup
/ login (with unverified-email resend + forgot-password) / email-verification landing / password
reset / Google+Apple OAuth buttons / session bootstrap + `useAuth()` + route guards / central
token-refresh + 401-retry / sign-out. New `lib/auth.ts` auth seam + `lib/auth-validation.ts`. The
**E2E harness** was reworked so authenticated E2E is real (stack-wired web build + API container with
`SUPABASE_JWT_SECRET`); validated locally against a real Supabase stack (signup/login/signout/redirect
green). Web gate green (135 vitest tests, 100% line / 99% branch over product code).

| | Item | Where | Status / decision | Noticed |
|---|---|---|---|---|
| ☑ | **4.3.1–4.3.8** auth screens + session/guards + 401-refresh/retry + sign-out | apps/web/src/pages/{Login,Signup,ForgotPassword,ResetPassword,AuthCallback}.tsx; components/{auth-provider,auth-context,route-guards,oauth-buttons,user-menu,auth-card,form-field}.tsx; lib/{auth,auth-validation,api-client}.ts | merged | 2026-06-27 |
| 🔒 | **Google + Apple OAuth live creds (owner).** The buttons render + call `signInWithOAuth`, but live creds are OWNER-ONLY (Google client id/secret; Apple needs the paid Developer acct — 2.1.2/2.1.3). Until wired, a click surfaces a friendly error; narrow/empty `VITE_OAUTH_PROVIDERS` to show a disabled "(soon)" button. | infra/supabase/oauth-setup.md; apps/web/src/components/oauth-buttons.tsx | owner — same as 2.1.2/2.1.3 | 2026-06-27 |
| ◐ | **OAuth-enable default (decision).** Task 4.3.5 verify wants the buttons "present and enabled"; the group note wants graceful degradation when unconfigured. **Default chosen:** both enabled by default (passes the verify + E2E) with a documented `VITE_OAUTH_PROVIDERS` lever to disable per environment, plus click-time error handling. Documented in `.env.example`. | apps/web/src/components/oauth-buttons.tsx; .env.example | decided (owner can narrow per env) | 2026-06-27 |
| ◐ | **401-retry covered in vitest, not E2E (decision).** Forcing a mid-session 401 against a healthy local API isn't reliably reproducible, so the 401→refresh-once→retry + refresh-fail→signout path is verified exhaustively in `src/lib/api-client.test.ts` and noted in `e2e/auth.spec.ts`. | apps/web/src/lib/api-client.test.ts | decided | 2026-06-27 |
| ◐ | **AuthProvider degrades to signed-out when Supabase env is absent.** Required so the intentionally env-less CI a11y build (and the local `playwright` smoke) still render (→ `/login`) instead of hanging on the loader; `readEnv`'s thrown message still names the missing var for a real misconfig. | apps/web/src/components/auth-provider.tsx | decided | 2026-06-27 |
| ☐ | **`supabase/config.toml` redirect entry added:** `http://127.0.0.1:4173/**` (CI Playwright preview origin) so the signup E2E `emailRedirectTo` is allow-listed. Compatible with `tests/test_auth_config.py`. | supabase/config.toml | done in 4.3 | 2026-06-27 |

**4.4 — Language management & CEFR level UI · DONE.** Active-language picker (header) + add/remove
languages (`/languages` screen) + sidebar CEFR level panel with band/progress/manual override, all
through the typed API client (Supabase stays auth-only). `ActiveLanguageProvider` persists the
selection per user (localStorage) and re-keys language-scoped queries so a switch refetches. Web gate
green (194 vitest, 100% line / 99.35% branch); `e2e/languages.spec.ts` validated against the real
ephemeral stack (all 4 e2e specs green, zero real LLM calls).

| | Item | Where | Status / decision | Noticed |
|---|---|---|---|---|
| ☑ | **4.4.1–4.4.5** active-language picker + persistence, add/remove (confirm dialog), CEFR panel (band/progress) + manual override | apps/web/src/components/{active-language-context,active-language-provider,language-picker,cefr-panel,add-language-form,remove-language-dialog}.tsx; lib/{languages,proficiency,cefr}.ts; pages/Languages.tsx; app-layout.tsx | merged | 2026-06-27 |
| ◐ | **Add-language reconciliation (decision).** Plan said "name + CEFR starting level/direction" but `POST /languages` takes name/code/vowelized ONLY. **Chosen:** create, then `PUT /proficiency/{id}` for a non-default starting band (A1 skipped — it's already the zero-score default); NO "direction" field — direction is derived from the language code (group 4.9). | apps/web/src/lib/languages.ts; components/add-language-form.tsx | decided | 2026-06-27 |
| ◐ | **CEFR progress-bar colour (decision).** "red/orange/blue/green-neutral" read as a by-tier palette over a neutral (muted) track: A1 red, A2 orange, B1/B2 blue, C1/C2 green, unknown → neutral. | apps/web/src/lib/cefr.ts | decided | 2026-06-27 |
| ◐ | **Active-language placement (decision).** Picker lives in the always-visible header (mobile-safe); the CEFR panel lives in the sidebar, which is `hidden sm:` (desktop-only). Mobile reachability of the sidebar panel is deferred to the responsive nav work (Phase 7); the picker — the load-bearing scoping control — stays reachable on mobile. 4.9 note: the `VowelMarksToggle` was placed INLINE at the top of each language screen (Generate/Review/Discover), NOT in the sidebar — so it is reachable on mobile where it matters (during review), independent of the desktop-only sidebar. | apps/web/src/components/app-layout.tsx; pages/{Generate,Review,Discover}.tsx | decided (CEFR-panel mobile = P7) | 2026-06-27 |
| ☐ | **E2E harness: authed-API support (no backend code change).** The `e2e` job's API container now gets `SUPABASE_JWKS_URL` (the local stack signs **ES256** tokens → verify via JWKS, NOT the HS256 `SUPABASE_JWT_SECRET`, which 4.3 set but never exercised against the API) and `CORS_ALLOW_ORIGINS=http://127.0.0.1:4173` (the preview origin) so the browser's cross-origin authed calls pass preflight. First group to make authed API calls in E2E. | .github/workflows/ci.yml | done in 4.4 | 2026-06-27 |
| ◐ | **Backend default CORS lacks the 4173 preview origin (minor).** A developer running the API + a local `vite preview` build against it would need `CORS_ALLOW_ORIGINS` set (defaults cover :5173/:3000 + capacitor). Not changed here (kept the backend untouched); could be added to `app/settings.py` defaults if local preview-against-API becomes common. | apps/api/app/settings.py | note (no action) | 2026-06-27 |
| ☑ | ~~**Create-time `vowelized` checkbox** is in the add-language form; the LIVE vowel-marks toggle + RTL/diacritic rendering is group 4.9.~~ **DONE in 4.9:** the live `VowelMarksToggle` (device-persisted `useVowelMarks`) strips/restores harakat/nikkud in displayed target text, shown only for vowelized languages; RTL direction + diacritic fonts land alongside. | apps/web/src/components/{vowel-marks-toggle,vowel-marks-provider}.tsx; lib/language-text.ts | done (4.9.3) | 2026-06-27 |

**4.5 — Generate screen · DONE.** Word-input form (textarea + live parsed-word chips + count) →
`POST /generate` (typed client, explicit in-progress state) → results grouped back into sentences
(recognition+production re-paired) shown with translation + used-word chips → per-sentence
select-and-save (default all) → `POST /cards/save` sending ONLY the selected sentences' cards, with a
success toast + saved confirmation and a "Generate more"/"Start over" reset. First-class friendly
cost-guard states: the **shared** `DailyLimitPanel` for the quota 429 (`daily_cap_reached` /
`daily_limit_reached`), plus inline `server_busy` / `rate_limited` / `email_unverified` / generic
states. New `lib/generate.ts` + `lib/llm-error.ts` + `components/daily-limit-panel.tsx`. Web gate
green (248 vitest, 100% line / 99.49% branch over product code — new files 100/100);
`e2e/generate.spec.ts` added (zero real LLM calls).

| | Item | Where | Status / decision | Noticed |
|---|---|---|---|---|
| ☑ | **4.5.1–4.5.4** word form + validation, generate + in-progress + sentence rendering, select-and-save (only selected), first-class shared daily-limit 429 panel | apps/web/src/pages/Generate.tsx; lib/{generate,llm-error}.ts; components/daily-limit-panel.tsx; lib/api-client.ts; e2e/generate.spec.ts | merged | 2026-06-27 |
| ◐ | **Word cap read from the schema, not hardcoded (decision).** `openapi-typescript` drops numeric constraints (`maxItems`), so a new deterministic `pnpm gen:api` step (`packages/api-types/scripts/generate-constants.mjs`) emits `src/constants.ts` `schemaLimits.generateWordsMaxItems` from `GenerateRequest.words.maxItems` (currently 30); the CI drift check now covers `src/constants.ts` too. The form warns + blocks past it (the server still 422s as the backstop). | packages/api-types/{scripts/generate-constants.mjs,src/constants.ts,package.json,src/index.ts}; .github/workflows/ci.yml | decided | 2026-06-27 |
| ◐ | **"Reviewable in Review" proven at the data layer (decision).** 4.5.3's verify wants saved cards "reviewable in Review", but the Review screen is group 4.6. The E2E proves it by hitting `GET /review/due` with the captured demo token (saved cards are `saved`+due-now → they appear), and the save mutation invalidates the whole `['review', ...]` query space so the 4.6 due query refetches once built. | apps/web/e2e/generate.spec.ts; apps/web/src/lib/generate.ts | decided (no owner action) | 2026-06-27 |
| ◐ | **Shared 429 panel placement (for 4.7 + 4.10.2).** The dedicated daily-limit panel lives in `components/daily-limit-panel.tsx` (gated on the quota-429 shape via `isDailyLimitError`); Discover (4.7) and the 4.10.2 sharing check import THIS component — no duplicated 429 UI. | apps/web/src/components/daily-limit-panel.tsx; lib/llm-error.ts | decided | 2026-06-27 |
| ☐ | **Generate words split on newlines/commas only** (not spaces) so multi-word phrases (e.g. "buenos días") stay intact; matches the server's per-entry cleaning. No dedupe (server doesn't dedupe). | apps/web/src/lib/generate.ts | note (no action) | 2026-06-27 |

**4.6 — Review screen (FSRS loop) · DONE.** `GET /review/due` (split new vs. due) → counts header +
progress bar → walk a stable client-side snapshot one card at a time → reveal the answer (recognition
= translation; production = the target sentence, tap-a-word enabled) → rate Again/Hard/Good/Easy in the
**LOCKED red/orange/blue/green** colours (`POST /review/{card_id}/grade`, FSRS 1–4) → advance. Clean
"all caught up" empty state + a "done for today / check for more" (refetch) completion state. Keyboard
shortcuts (space/enter reveal, 1–4 rate). Tap-a-word popover on production cards via `POST /explain`
(keyed by word + language; instant from the card's pre-generated note when present). New `lib/review.ts`
+ `components/tappable-sentence.tsx`. Web gate green (301 vitest, 100% line / 99.58% branch / 100% func
over product code — `review.ts` 100/100/100); `e2e/review.spec.ts` added (zero real LLM calls).

| | Item | Where | Status / decision | Noticed |
|---|---|---|---|---|
| ☑ | **4.6.1–4.6.5** due batch (new/due counts + empty state), reveal (recognition/production variants), rate in locked red/orange/blue/green + advance, tap-a-word explain popover (word+language key), keyboard shortcuts | apps/web/src/pages/Review.tsx; lib/review.ts; components/tappable-sentence.tsx; e2e/review.spec.ts | merged | 2026-06-27 |
| ◐ | **Grading walks a snapshot — no refetch on grade (decision).** The due batch is loaded once per language and walked client-side (mirrors the legacy snapshot walk); grading does NOT invalidate the due query, so the queue can't reshuffle mid-review. It refreshes on remount, on "check for more", and when cards are saved (4.5 invalidates `['review', …]`). | apps/web/src/lib/review.ts; pages/Review.tsx | decided (no owner action) | 2026-06-27 |
| ◐ | **Client `bareWord` mirrors the backend `STRIP_CHARS` exactly (decision).** Tap-a-word strips punctuation identically to `lengua_core.cards.bare_word` (incl. the Arabic `؟،؛` marks; `¿/¡` are NOT stripped) so a tapped word matches the key the backend stored its explanation under. If the backend ever changes `STRIP_CHARS`, update `lib/review.ts` in lockstep. | apps/web/src/lib/review.ts; apps/api/lengua_core/cards.py | note (keep in sync) | 2026-06-27 |
| ◐ | **Explain query keyed by word + language (decision).** Per the 4.6.4 verify, `useExplainWord` keys `['explain', languageId, word]` (a word's gloss in a language is stable; the backend caches per bare word too). Trade-off: the same word in two different sentences shares one cached explanation — acceptable here and matches the backend's per-word cache. | apps/web/src/lib/review.ts | decided | 2026-06-27 |
| ☑ | ~~**Tap-a-word is whitespace-tokenised (LTR-correct now; RTL refinement is 4.9.4).**~~ **DONE in 4.9.4:** `segmentSentence` (whitespace split + bare-word strip) is already direction-agnostic and produces correct word spans for RTL strings — kept (NOT swapped for `Intl.Segmenter`) so the client tokenisation stays byte-identical to the backend's, which is what makes a cached-explanation lookup match. `TappableSentence` now derives dir+font from the language code, anchors the popover RTL, and keys the lookup off the canonical word WITH its marks (so a vowel-stripped display still hits the cached note). Tested via touch (`.tap()`) + click in `e2e/rtl.spec.ts` and RTL segmenter unit tests. | apps/web/src/components/tappable-sentence.tsx; lib/{language-text,review}.ts | done (4.9.4) | 2026-06-27 |
| ☐ | **Review header omits the CEFR band (decision).** The new/due counts header is the 4.6.1 requirement; the band already shows in the sidebar `CefrPanel`, so Review isn't coupled to the proficiency query. Revisit if a band-in-header is wanted. | apps/web/src/pages/Review.tsx | note (no action) | 2026-06-27 |
| ☑ | **Seed bug fixed: E2E demo cards now carry an `fsrs_state` (deviation).** The Review E2E was the first to GRADE a seeded card and surfaced that `scripts/seed_e2e.py` inserted demo cards with `fsrs_state IS NULL`, which the grade endpoint rejects with **422** (`Card … has no FSRS state to grade.`). Fixed the seed to write a real fresh state via `lengua_core.scheduler.new_card_state()` (the same state the save service writes), so seeded cards are gradeable exactly like real saved ones; they stay `new` + due-now, so `test_demo_seed` is unaffected. `scripts/seed_dev_user.py` may have the same gap (not exercised by the E2E) — worth a follow-up. | apps/api/scripts/seed_e2e.py | fixed in this PR | 2026-06-27 |

**4.7 — Discover screen · DONE.** Count (defaulting to the user's `discover_count` from `GET /settings`)
+ optional topic form → `POST /discover` previews new words → accept (handed into the existing Generate
flow, group 4.5) or reroll (refetch + replace). The **shared** `DailyLimitPanel` covers the quota 429,
and a new **shared** `LlmErrorState` renders the friendly transient/verify/generic cost-guard states for
BOTH Generate and Discover (Generate refactored onto it — no duplicated error UI). New
`lib/{discover,settings,generate-handoff}.ts` + `components/llm-error-state.tsx`. Web gate green (353
vitest, 100% line/branch/func over the new product code); `e2e/discover.spec.ts` added (zero real LLM calls).

| | Item | Where | Status / decision | Noticed |
|---|---|---|---|---|
| ☑ | **4.7.1–4.7.3** count(+topic) form defaulting to the settings `discover_count`, suggested-words preview, accept→Generate handoff + reroll, shared daily-limit 429 + friendly states | apps/web/src/pages/Discover.tsx; lib/{discover,settings,generate-handoff}.ts; components/llm-error-state.tsx; e2e/discover.spec.ts | merged | 2026-06-27 |
| ◐ | **Accept hands off to the Generate flow, not `POST /discover/accept` (decision).** The task says "feed into the generate flow … do NOT duplicate the generate UI", so accept stashes the words in a one-shot in-memory store (`lib/generate-handoff.ts`) + `navigate('/generate')`, and the Generate workspace consumes them once on mount (prefills the word input). This reuses the whole generate→review→select→save UI (the user reviews before saving) instead of `POST /discover/accept` (which auto-generates+saves with no review step). A tiny module store, not router `location.state`, gives correct one-shot semantics across the per-language remount. `POST /discover/accept` stays in the API, just unused by the web app. | apps/web/src/lib/generate-handoff.ts; pages/{Discover,Generate}.tsx | decided (no owner action) | 2026-06-27 |
| ◐ | **Discover count bounds read from the schema, not hardcoded (decision).** Extended the `gen:api` constants step to emit `schemaLimits.discoverCount{Min,Max,Default}` from `DiscoverRequest.count` (minimum/maximum/default = 1/20/5); the form clamps to these + falls back to the default. Mirrors 4.5's `generateWordsMaxItems`; same CI drift check (`src/constants.ts`). | packages/api-types/{scripts/generate-constants.mjs,src/constants.ts}; apps/web/src/lib/discover.ts | decided | 2026-06-27 |
| ◐ | **Shared `LlmErrorState` extracted (decision).** Generate (4.5) had the daily-limit-vs-inline-friendly-error logic inline; Discover needs the same, so it moved into `components/llm-error-state.tsx` (renders the shared `DailyLimitPanel` for the quota 429, else a friendly card from `describeLlmError` with an optional transient hint). Generate was refactored onto it — no duplicated 429/error UI (reinforces the 4.10.2 sharing requirement). | apps/web/src/components/llm-error-state.tsx; pages/{Generate,Discover}.tsx | decided | 2026-06-27 |
| ◐ | **Reroll freshness is a backend property (note).** Against a real backend, a reroll with identical `(language, topic, count)` may return the SAME words within the short discover-reuse window (3.6.3), and the deterministic FakeLLM always returns the same pool order — so the "new set replaces old" assertion is proven via browser-boundary stubs in `e2e/discover.spec.ts`. The screen always refetches + replaces whatever comes back; it does not try to bust the server cache. | apps/web/src/lib/discover.ts; e2e/discover.spec.ts | note (no action) | 2026-06-27 |
| ☑ | **Settings read-only data layer added (`lib/settings.ts`).** Started as just `useSettingsQuery` (`GET /settings`) + the `discover_count` key for Discover's default count; **group 4.8 extended it** with `useUpdateSettings` (`PUT /settings` → `setQueryData`), the `SETTINGS_FIELDS` model + bounds, and pure `validateSettingValue`/`initialSettingValue`. | apps/web/src/lib/settings.ts | done (4.7 read + 4.8 editor) | 2026-06-27 |
| ☐ | **Discover count input is min=1/max=20 with a validation hint (note).** The form disables Discover + warns when the count is outside the request bounds (and clamps defensively on submit) so the server never 422s. No spaces in the topic are stripped beyond trim; a blank topic is sent as `null`. | apps/web/src/pages/Discover.tsx | note (no action) | 2026-06-27 |

**4.8 — Settings & Account screens · PR OPEN (PAUSE — manager review of the irreversible account-deletion UX).** A **Settings** screen edits the three per-user prefs (daily new-card limit, daily total limit, discover count) → `PUT /settings` with per-field bounds validation. An **Account** screen shows the signed-in email + sign-out, exports the full data bundle (`GET /account/export` → client-side JSON download), and hard-deletes the account behind a confirm-TYPED dialog (`DELETE /account` exactly once → sign out + `queryClient.clear()` → `/login`; 502-retryable surfaced friendly). New `lib/account.ts` + Settings/Account data layer in `lib/settings.ts` + `components/delete-account-dialog.tsx`. Web gate green (390 vitest, 100% line / 99.66% branch over product code — all new files 100/100; lint/format/typecheck/build clean); `e2e/{settings,account}.spec.ts` added (zero real LLM calls; the demo account is never actually deleted — the delete E2E stubs `DELETE /account` at the browser boundary).

| | Item | Where | Status / decision | Noticed |
|---|---|---|---|---|
| ☑ | **4.8.1–4.8.3** Settings editor (3 prefs + bounds validation + save) · Account profile/sign-out + data-export download · confirm-typed hard-delete → signout+redirect | apps/web/src/pages/{Settings,Account}.tsx; components/delete-account-dialog.tsx; lib/{account,settings}.ts; e2e/{settings,account}.spec.ts | PR open (PAUSE) | 2026-06-27 |
| ◐ | **"Server bounds" reconciliation (decision).** `PUT /settings` is a generic key/value store with NO per-value bound. **Chosen:** validate `discover_count` against the REAL schema bound (`DiscoverRequest.count` min/max via `schemaLimits` — the `/discover` endpoint 422s outside it); validate the two daily review limits against the legacy app's product bounds (new 1–100, total 1–500), documented as client-side product bounds in `lib/settings.ts`. | apps/web/src/lib/settings.ts | decided | 2026-06-27 |
| ☑ | ~~**Backend gap: review batch ignores the per-user `daily_new_limit`/`daily_total_limit`.**~~ **CLOSED in 4.8b:** `GET /review/due` now reads the user's settings via `SettingsService` and passes parsed limits into `due_split(new_limit, total_limit)` (pure unit-tested `resolve_review_limit`/`resolve_review_limits` in `app/services/review.py`; missing/blank/non-numeric/non-positive → `lengua_core.config` default). Integration tests prove a per-user limit bounds the batch. | apps/api/app/routers/review.py; app/services/review.py | done (4.8b) | 2026-06-27 |
| ◐ | **Settings save writes ALL three fields, defaults included (decision).** Mirrors the legacy Streamlit "Save settings" (it wrote all values). PUT merges, so other keys (e.g. the per-kind LLM caps) are untouched; the Discover default count is written as its current value (5 when unset), so the Discover spec's "defaults to 5" assertion is unaffected. | apps/web/src/pages/Settings.tsx | decided | 2026-06-27 |
| ◐ | **Delete confirmation phrase = `delete my account` (decision).** A fixed lowercase sentence (trim-then-exact match) rather than the account email — clear + intentional, hard to fire by accident. The delete is a `<form>` so the submit handler re-checks "confirmed && not pending" (defense in depth; the submit button is also disabled), proven by a direct `fireEvent.submit` test. | apps/web/src/components/delete-account-dialog.tsx | decided | 2026-06-27 |
| ◐ | **`useUpdateSettings` uses `setQueryData`, not `invalidateQueries` (decision).** `PUT /settings` returns the full authoritative map, so writing it straight into the cache is refetch-free and keeps Discover's `useSettingsQuery` instantly in sync. | apps/web/src/lib/settings.ts | decided | 2026-06-27 |
| ☐ | **App routing test now wraps a `QueryClientProvider` (test-harness update).** Settings/Account went from inert `PlaceholderScreen` stubs to provider-dependent screens (the delete dialog calls `useQueryClient`), so `App.test.tsx` adds a QueryClient + stubs the settings/account data hooks — mirroring the existing `@/lib/languages` stub. No product behavior change. | apps/web/src/App.test.tsx | done in 4.8 | 2026-06-27 |

**4.8 — Manager adversarial review (3-lens, pre-merge) + hardening.** Verdict: 1 `block` + 2
`merge_with_nits`, converging on one real defect — the post-delete teardown was not resilient.
**Hardened in the PR before merge** (`delete-account-dialog.tsx`, `lib/auth.ts`, `lib/account.ts`
+ tests, web gate still 100% line / 99.68% branch):

| | Item | Where | Status |
|---|---|---|---|
| ☑ | **Resilient post-delete teardown.** `onSuccess` now signs out **locally** (`signOutLocal` = `signOut({scope:'local'})`, no network logout that would fail on the just-deleted user and leave the local session intact → `RedirectIfAuthed` bounce) and the cache-clear + redirect run **unconditionally** (`signOutLocal().catch(() => undefined)`), so a failed sign-out can't strand the deleted user logged-in. New `signOutLocal` + tests; new dialog test proves teardown completes even when local sign-out rejects. | apps/web/src/components/delete-account-dialog.tsx; lib/auth.ts | hardened | 2026-06-27 |
| ☑ | **Dialog can't be dismissed mid-flight.** `onOpenChange` ignores Escape/overlay-close while the irreversible DELETE is pending (was: reset the mutation + silently drop a retryable 502). + a synchronous `inFlight` ref latch makes exactly-once independent of render timing (same-tick double-submit). Tests added. | apps/web/src/components/delete-account-dialog.tsx | hardened | 2026-06-27 |
| ☑ | **Export download revokes the object URL on the NEXT tick**, not synchronously (a same-tick revoke can abort the download in Safari/Firefox; Chromium-only Playwright misses it). Test updated. | apps/web/src/lib/account.ts | hardened | 2026-06-27 |
| ☑ | ~~**ESCALATED — daily new/total limit settings persist but have ZERO effect (parity regression).**~~ **FIXED in 4.8b (this PR):** `review_due` now wires the user's `daily_new_limit`/`daily_total_limit` into `due_split(new_limit, total_limit)` (parity with legacy Streamlit restored); the false `app/schemas/settings.py` docstring ("the Phase 3 quota gate reads these") is corrected to say where each key is actually consumed (review batch vs. discover vs. the cost-guard `daily_cap_*` keys); backend tests prove a per-user limit bounds the batch (and that missing/blank/invalid falls back to the config default); the Settings form adds cross-field `new ≤ total` validation (inline error, blocks save). | apps/api/app/routers/review.py; app/services/review.py; app/schemas/settings.py; apps/web/src/lib/settings.ts | done (4.8b) | 2026-06-27 |
| ☐ | **From 4.6 (logged):** `scripts/seed_dev_user.py` may insert cards with `fsrs_state IS NULL` (the same gap 4.6 fixed in `seed_e2e.py`), which the grade endpoint 422s — not exercised by E2E. Small seed fix. | apps/api/scripts/seed_dev_user.py | follow-up | 2026-06-27 |

**4.8b — Backend: honor the per-user daily review limits (parity must-fix) · DONE.** `GET /review/due`
(`app/routers/review.py`) now reads the authenticated user's settings through the existing
`SettingsService` (repositories-only, no raw SQL in the router) and passes the resolved limits into
`ReviewService.due_split(new_limit=…, total_limit=…)`, so editing the daily new/total limits on the
web Settings screen actually bounds the due batch again (legacy-Streamlit parity restored). The parse
rule lives in two pure, unit-testable helpers (`resolve_review_limit` / `resolve_review_limits` in
`app/services/review.py`): a stored string → positive int, and any missing / blank / non-numeric /
non-positive value → the `lengua_core.config` default (`DAILY_NEW_LIMIT` / `DAILY_TOTAL_LIMIT`), so a
cleared or malformed setting never shrinks the batch to nothing or 500s. The false
`app/schemas/settings.py` docstring ("the Phase 3 quota gate reads these") is corrected to document
where each key is consumed (review batch ← `daily_*_limit`; discover ← `discover_count`; cost-guard
caps ← `daily_cap_*`). Frontend: the Settings form adds cross-field validation
(`crossFieldSettingError` in `lib/settings.ts`) so `daily_new_limit ≤ daily_total_limit` (inline error
on the new-cards field, blocks save) now that the values drive the batch. Backend gate green (464
tests, 100% line+branch; ruff + mypy --strict clean; the 2 new integration tests prove a per-user
limit bounds the batch + the fallback path). Web gate green (`corepack pnpm --filter web verify` exit
0; settings files 100%). `openapi.json` + `packages/api-types` regenerated (only the `/review/due`
route **description** changed — no schema/response delta). Touches `apps/api/app/routers/review.py`,
`app/services/review.py`, `app/schemas/settings.py`, `apps/web/src/lib/settings.ts`, and
`pages/Settings.tsx`.

**4.9 — RTL, diacritics & complex scripts · DONE.** Per-language right-to-left direction,
diacritic-correct self-hosted fonts, a vowel-marks toggle, and RTL-aware tap-a-word, on the
Generate/Review/Discover screens. New pure helpers in `lib/language-text.ts`
(`directionForCode`/`isRtlCode` — Arabic/Hebrew & their script-mates → rtl, else ltr;
`scriptFontClass`; `stripDiacritics`/`hasDiacritics`/`displayText` over a precise harakat+nikkud
range). New `components/language-text.tsx` (`<LanguageText>` renders target text with dir + script
font + the toggle applied) and the `VowelMarksProvider`/`useVowelMarks` seam +
`VowelMarksToggle` (device-persisted like the theme, default ON, self-gating to vowelized
languages). Fonts: `@fontsource/noto-naskh-arabic` + `@fontsource/noto-sans-hebrew` imported in
`main.tsx` and bundled by Vite (the woff2 land in `dist/assets` — **no runtime CDN**, mobile-webview-safe);
`font-arabic`/`font-hebrew` Tailwind utilities. `TappableSentence` refactored to derive dir+font from
the language code, strip glyphs per the toggle, and **key the explain lookup off the canonical bare
word WITH marks** (so a vowel-stripped display still hits the card's cached note).

| | Item | Where | Status / decision | Noticed |
|---|---|---|---|---|
| ☑ | **4.9.1** per-language `dir` on each screen's content region (+ `LanguageText`/`TappableSentence`) | apps/web/src/lib/language-text.ts; pages/{Generate,Review,Discover}.tsx | done | 2026-06-27 |
| ☑ | **4.9.2** self-hosted Noto Naskh Arabic + Noto Sans Hebrew, bundled (no CDN), applied via `font-arabic`/`font-hebrew` | apps/web/src/main.tsx; tailwind.config.ts; lib/language-text.ts | done | 2026-06-27 |
| ☑ | **4.9.3** vowel-marks toggle (strip/restore harakat/nikkud), device-persisted, self-gating to vowelized langs | apps/web/src/components/{vowel-marks-context,vowel-marks-provider,vowel-marks-toggle}.tsx | done | 2026-06-27 |
| ☑ | **4.9.4** RTL-aware tap-a-word (touch + click); RTL segmenter unit tests; canonical-word lookup | apps/web/src/components/tappable-sentence.tsx; lib/review.ts; e2e/rtl.spec.ts | done | 2026-06-27 |
| ◐ | **Direction is code-derived (decision).** RTL = Arabic/Hebrew script primary subtags (`ar/fa/ur/ps/sd/ug/ckb` + `he/iw/yi`), matched on the first subtag case-insensitively — no manual direction field (4.4 decision). Latin/unknown/missing → ltr. | apps/web/src/lib/language-text.ts | decided | 2026-06-27 |
| ◐ | **Segmenter kept whitespace-based, NOT `Intl.Segmenter` (decision).** Byte-identical to the backend's whitespace tokenisation so cached-explanation keys match; Hebrew maqaf-joined words stay one token (matches the backend). Diacritics are retained in the bare word; only Arabic punctuation (`؟،؛`) is stripped. | apps/web/src/lib/review.ts | decided | 2026-06-27 |
| ◐ | **Vowel-marks preference is device-global, NOT per-language (decision).** Mirrors the theme (one localStorage key, default ON); the toggle only SHOWS for vowelized languages. Cross-device sync via `PUT /settings` is a possible future nicety (logged, non-blocking). | apps/web/src/components/vowel-marks-provider.tsx | decided | 2026-06-27 |
| ◐ | **Visual snapshot = attached screenshot + deterministic assertions (decision).** `toHaveScreenshot` baselines are platform-specific (can't generate the Linux-CI baseline from Windows → would red the first CI run), so `e2e/rtl.spec.ts` asserts `dir="rtl"`, `document.fonts.check`, and nikkud-present/stripped deterministically, and ATTACHES a screenshot as the human-reviewable "visual snapshot". | apps/web/e2e/rtl.spec.ts | decided | 2026-06-27 |
| ◐ | **E2E seed gained a vowelized Hebrew (nikkud) deck (decision).** `scripts/seed_e2e.py` adds a second `Hebrew`/`he`/`vowelized` language + nikkud recognition+production cards — additive + idempotent; the returned `SeedResult` still reports Spanish as primary, so existing seed/demo assertions are unaffected. Needed because FakeLLM can't emit real nikkud. | apps/api/scripts/seed_e2e.py | decided | 2026-06-27 |
| ☐ | **Content-region `dir` mirrors English chrome too (note).** Setting `dir="rtl"` on the screen `<section>` right-aligns the (short) English headings/labels within RTL screens — intentional (the screen is in an RTL context). App shell (header/sidebar/nav) stays LTR. Full logical-property mirroring of every physical Tailwind class is deferred (not required for the verifies). | apps/web/src/pages/{Generate,Review,Discover}.tsx | note (no action) | 2026-06-27 |

**4.9 — Web gate green** (`corepack pnpm --filter web verify` exit 0): 446 vitest, 100% line /
99.68% branch over product code (only the pre-existing `api-client.ts` line-213 branch is <100;
all new 4.9 files 100/100), eslint + prettier + tsc clean, `vite build` bundles the fonts. Backend
seed change is ruff + ruff format + mypy --strict clean. The full Playwright RTL spec + cross-platform
gate run in GitHub Actions CI.

**4.10 — Cross-cutting UX states & consent · DONE.** Three shared state components consolidate the
previously-bespoke per-screen affordances: `LoadingState` (a content skeleton over a new
`ui/skeleton` primitive, with an sr-only label), `EmptyState` (icon + title + action; neutral or
celebratory `success` tone), and `ErrorState` (a retryable error card). The active-language context
now exposes `refetch`, so Generate/Review/Discover render the shared skeleton while languages load, a
retryable error when the languages query fails (previously a languages error fell through to the
"add a language" empty state — now distinguished), and the shared empty card; Review's due-batch
loading/empty/error route through the same components, and the "all caught up" state is the `success`
`EmptyState`. 4.10.2 formalized the single shared 429 `DailyLimitPanel` (already built in 4.5/4.7): a
source-scan test (`daily-limit-panel.shared.test.ts`) proves the panel UI lives in exactly one file
and that Generate + Discover both reach it via the shared `LlmErrorState` → `DailyLimitPanel` path
(no duplicate 429 UI), and the panel test now asserts it's inert for a non-quota 429. 4.10.3 added the
first-run analytics-consent seam: `lib/analytics.ts` boots analytics at most once and ONLY after an
explicit opt-in AND with `VITE_POSTHOG_KEY` set, via `AnalyticsConsentProvider` +
`AnalyticsConsentBanner` (mounted app-global in `main.tsx`), persisted so it never re-prompts. Web
gate green (`corepack pnpm --filter web verify` exit 0; 477 vitest, 100% line/func, 99.7% branch over
product code — all new files 100/100; `e2e/consent.spec.ts` added).

| | Item | Where | Status / decision | Noticed |
|---|---|---|---|---|
| ☑ | **4.10.1** shared `LoadingState`/`EmptyState`/`ErrorState` (+ `ui/skeleton`) wired into Generate/Review/Discover; context gains `refetch` for the retryable languages-error | apps/web/src/components/{loading-state,empty-state,error-state,ui/skeleton}.tsx; active-language-{context,provider}; pages/{Generate,Review,Discover}.tsx | done | 2026-06-27 |
| ☑ | **4.10.2** formalized the single shared 429 `DailyLimitPanel` — source-scan proves Generate+Discover both consume it via `LlmErrorState` (no dup); panel inert for non-quota 429 | apps/web/src/components/daily-limit-panel.shared.test.ts; daily-limit-panel.test.tsx | done (no refactor needed — no duplication existed) | 2026-06-27 |
| ☑ | **4.10.3** first-run analytics-consent — opt-in-gated `initAnalytics` + provider/banner, persisted, app-global | apps/web/src/lib/analytics.ts; components/analytics-consent-{context,provider,banner}.tsx; main.tsx; e2e/consent.spec.ts | done | 2026-06-27 |
| ☑ | **Fold-in (auth security-review nit):** the `RequireAuth → /login → back` redirect now preserves the FULL target location (pathname **+ search + hash**), not just `from.pathname` — a deep link like `/review?tab=due#card-3` survives the login round-trip | apps/web/src/components/route-guards.tsx (+ test) | done | 2026-06-27 |
| ◐ | **PostHog wiring deferred to Phase 5/8 (decision; non-blocking).** 4.10.3 is the consent SEAM only: `lib/analytics.ts`'s default initializer is a documented no-op, so even with consent + a key nothing loads until Phase 5/8 registers the real `posthog-js` loader via `setAnalyticsInitializer`. Conservative default chosen: behind the `VITE_POSTHOG_KEY` env flag, so dev/CI/E2E (no key) ship zero analytics and the E2E proves no analytics request fires. No `posthog-js` dependency added yet. | apps/web/src/lib/analytics.ts | decided (Phase 5/8 registers the real loader) | 2026-06-27 |
| ◐ | **Consent banner pre-dismissed in app E2E (decision).** The banner is a `fixed` bottom overlay; to keep it from intercepting clicks on bottom-anchored controls, a shared `e2e/fixtures.ts` seeds `analytics-consent=denied` via an init script for the app specs. The dedicated `consent.spec.ts` imports the RAW `@playwright/test` so it still exercises the genuine first-run banner. | apps/web/e2e/fixtures.ts; e2e/*.spec.ts | decided | 2026-06-27 |
| ◐ | **Vowel-marks/consent are device-local, not synced (note, consistent with 4.9).** The analytics decision (like the theme + vowel-marks pref) lives in localStorage per device; cross-device sync is a possible future nicety (non-blocking). | apps/web/src/lib/analytics.ts | note (no action) | 2026-06-27 |

**4.11 — Legacy Streamlit retirement note · DONE.** [`docs/streamlit-parity.md`](../docs/streamlit-parity.md)
is the parity checklist: it maps every legacy surface — home (`app.py`), the always-present sidebar
(`ui.py`: active-language picker, vowel-marks flag, CEFR band + progress + manual override, add/remove
languages), and each `pages/*` page (Generate, Review incl. tap-a-word + locked red/orange/blue/green
ratings, Discover, Settings) — to its reachable React screen/route/component, all `pages/*` features ✅.
The README "Legacy Streamlit" table row + a new prose section are both marked **deprecated — retained
for reference** (legacy code NOT deleted; stays runnable as a reference/fallback until prod (P6) +
mobile (P7)); the `docs/` index was updated to list the new doc. No code touched in `apps/api` or
`apps/web` (doc-only PR; legacy app untouched + still runnable).

| | Item | Where | Status / decision | Noticed |
|---|---|---|---|---|
| ☑ | **4.11.1** parity checklist doc + README "deprecated — retained for reference" (legacy code kept) | docs/streamlit-parity.md; README.md; docs/README.md | done | 2026-06-27 |
| ☐ | **✅\* nuance — flip `vowelized` on an _existing_ language isn't UI-wired.** Legacy could toggle the generation-vocalization flag on the active language anytime; React only sets it at language creation. Backend `PATCH /languages/{id}` already supports it → small UI follow-up (a 4.4/4.9-style control), NOT a missing capability; the separate device-level display vowel-marks toggle IS present. Safe default: documented as a follow-up, not blocking parity (demo languages are seeded with the right flag). | apps/web/src/components/add-language-form.tsx; (backend PATCH exists) | follow-up (non-blocking) | 2026-06-27 |
| ◐ | **✅\* by design — Discover "accept" routes through Generate.** Legacy previewed+saved in-page; React feeds accepted words into the reused Generate flow (`generate-handoff` → `/generate`) to keep the review-and-select-before-save step (rather than auto-saving via `POST /discover/accept`). End-to-end capability fully present; save UI is the shared Generate one. | apps/web/src/lib/generate-handoff.ts; pages/Discover.tsx | decided (group 4.7 reconciliation) | 2026-06-27 |
| ♻️ | **Gemini model selector intentionally retired.** The legacy Settings "Gemini model" selectbox has no React counterpart by design — the LLM provider/model is now operator/server config (`LLM_PROVIDER`: Groq for dev/CI, Gemini for prod), not a user-facing setting. Recorded so it isn't mistaken for a parity gap. | apps/api/app/settings.py; legacy pages/4_Settings.py | decided (architecture change) | 2026-06-27 |
