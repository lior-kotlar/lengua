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
| ☐ | Entire `apps/web/src` is the Phase 0 scaffold — `Home.tsx` renders only "Web shell scaffold" + a sample button | apps/web/src/pages/Home.tsx:8; apps/web/README.md:6 | Phase 4 |
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
| 3 — LLM quota & cost guard | 35 | usage counters, per-user caps, sliding-window rate limit, global kill-switch, abuse guard, BYOK seam |
| 4 — React web app | 51 | app shell, typed API client, auth screens, generate/review/discover/settings, RTL+diacritics, Streamlit retirement |
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
| ☑ | ~~**Phase 3 / `llm_budget` privilege**~~ — CLOSED in group 3.1 (PR open, pre-merge): `REVOKE ALL ON llm_budget FROM authenticated, anon` + SECURITY DEFINER increment/read functions `EXECUTE`-granted to `service_role` ONLY; the backend reaches the kill-switch only via the privileged `app.deps.get_usage_db` session, never `get_db`. Proven by `tests/test_rls.py` (authenticated denied SELECT/UPDATE + no EXECUTE). | high (Phase 3) | migration 0004; supabase/migrations/20260626120000_llm_killswitch.sql |
| ⚠ | **Prod transaction-pooler caveat:** asyncpg's prepared-statement cache breaks against Supabase's transaction pooler (6543) unless `statement_cache_size=0` / session pooler. RLS itself is pooler-safe (SET LOCAL re-applied per txn). Confirm prod `DATABASE_URL` **before Phase 6 deploy**. | medium (Phase 6) | apps/api/app/db/session.py:50 |
| ☐ | Migration drift test hardcodes predicate strings instead of parsing the canonical SQL — the "byte-for-byte match" isn't self-checking. | nit | apps/api/tests/db/test_rls_migration.py |
| ☐ | Latent footgun: any future session obtained **not** via `app.deps.get_db` runs as table owner (postgres) and silently bypasses RLS — add a boundary comment/guard as the surface grows. | nit | apps/api/app/db/rls.py |

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

## 9. Phase 3 (LLM quota & cost guard) — open questions for owner · logged, not blocked

Phase 3 is being driven autonomously (owner asked to complete it without pausing). I'm proceeding
with safe, conservative defaults; **confirm/adjust these later:**

**Progress:** 🛠 **3.1 landed (PR open, NOT yet merged)** — usage accounting + the server-only
kill-switch privilege model (Alembic `0004` + canonical `20260626120000_llm_killswitch.sql`,
`UsageRepository`, privileged `get_usage_db`; 379 tests green, 100% line+branch cov). Held for the
cost-guard 3-lens adversarial review before merge. 3.2–3.9 not started.

| | Question / decision | Default I'm using | Task |
|---|---|---|---|
| ❓ | **`GLOBAL_DAILY_BUDGET`** — project-wide daily LLM-call ceiling, "set below the active provider's free RPD". Needs a real number vs Groq `llama-3.1-8b-instant` free-tier requests/day. | a conservative value comfortably below Groq's free daily limit; documented in `.env.example` with a pointer to the provider RPD | 3.4.1 |
| ❓ | **Per-user daily caps + hard server maxima** (`MAX_GENERATE/DISCOVER/EXPLAIN_PER_DAY`) + defaults. | modest env-overridable defaults | 3.2.1 |
| ❓ | **`RATE_LIMIT_PER_MIN`** per user. | a modest default | 3.3.2 |
| ⚠ | **Rate-limiter backend**: in-process (slowapi, single instance) vs Postgres/Upstash sliding-window (multi-instance). Cloud Run may scale >1 instance (Phase 6) → in-process under-counts. | start in-process behind a `RateLimiter` interface; **flag the multi-instance swap for Phase 6** | 3.3.1 |
| ❓ | **Signup-abuse guard** — day-0 cap / cooldown value; where a captcha would slot in. | reduced first-day cap (env-configurable); captcha documented only, not built | 3.7.2 |
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
