# Phase 3 — LLM quota, rate-limiting & cost guard

> **Effort:** M  ·  **Depends on:** Phase 2 complete (auth + RLS + verified email)  ·  **Unlocks:** Phase 4
> **Source:** roadmap Phase 3 (../02-roadmap.md) · deep dive (../03-backend.md)
> The per-PR quality gate (../09-testing-quality.md) applies to EVERY task below: each lands via a PR that is 100% green + ≥80% coverage (backend & frontend) + Playwright E2E. A task is not done until its tests keep coverage ≥80%.

**Goal:** The operator-funded LLM key can never produce a bill — per-user daily caps, per-user rate limits, and a global daily kill-switch (all provider-agnostic: Groq now, Gemini later) hold under a load test with zero paid usage, and every blocked call returns a friendly message and emits a metric/span.

**Status legend:** [ ] todo · [~] in progress · [x] done · [!] blocked

---

## 3.1 — Usage accounting tables & atomic counters  ·  M

_Context: every gate reads and writes counters; this group lays the durable accounting layer the rest of the phase depends on._

- [x] **3.1.1** Confirm the `llm_usage` (`user_id`, `day`, `kind`, `count`, PK `(user_id, day, kind)`) and `llm_budget` (`day` PK, `count`) tables created in Phase 1 (1.4.3) match 03-backend.md, including the `llm_usage.user_id → profiles(id) on delete cascade` FK (the committed schema renamed the historical `gemini_*` tables to `llm_*`). No column/FK was missing, so no table changes; Alembic `0004` only adds the new kill-switch privilege objects (see 3.1.2/3.1.3).
      verify: `pytest tests/db/test_usage_tables.py` — on a clean `alembic upgrade head` DB both tables exist with the right columns, composite/PKs, and the `on delete cascade` FK from `llm_usage.user_id`→`profiles.id`; migration `0004` round-trips (`alembic downgrade -1`→`upgrade head`).
      depends: Phase 1 (1.4.3 usage tables)
- [x] **3.1.2** `llm_usage` already has its RLS owner policy (`user_id = auth.uid()`, Phase 2.6). `llm_budget` is the GLOBAL kill-switch and is made **server-only**: Alembic `0004` + canonical `supabase/migrations/20260626120000_llm_killswitch.sql` `REVOKE ALL ON llm_budget FROM authenticated, anon`, add `SECURITY DEFINER` `increment_llm_usage`/`get_llm_budget_count` (owned by `postgres`), and `GRANT EXECUTE` to `service_role` ONLY (not `authenticated`, so PostgREST RPC can't trip the kill-switch). The backend reaches it via the privileged `app.deps.get_usage_db` session.
      verify: `pytest tests/test_rls.py` — user A cannot select user B's `llm_usage` rows; an `authenticated` session is denied SELECT/UPDATE on `llm_budget` and has no EXECUTE on either function, while a privileged/`service_role` path can.
- [x] **3.1.3** Repository helper `UsageRepository.increment_usage(user_id, kind, day)` calls the `SECURITY DEFINER` `increment_llm_usage(...)`, which atomically upserts `llm_usage` and bumps `llm_budget` for the day in one statement (row-locked `insert ... on conflict do update set count = count + 1`) and returns the new budget count.
      verify: `pytest tests/repositories/test_usage_repo.py::test_increment_is_atomic` — 50 concurrent increments via asyncio (each on its own session) leave `count == 50` in both tables (no lost updates).
- [x] **3.1.4** Repository reads `UsageRepository.get_user_daily_count(user_id, kind, day)` and `get_budget_count(day)` returning 0 when no row exists yet.
      verify: `pytest tests/repositories/test_usage_repo.py::test_reads_default_zero` passes for a fresh user/day.

## 3.2 — Per-user daily caps  ·  M

_Context: each LLM `kind` (generate / discover / explain) has a per-user daily ceiling from `user_settings`, clamped by a hard server maximum so a user can't raise their own cap past the operator limit._

- [x] **3.2.1** Typed quota config in `pydantic-settings` (`app/settings.py`): hard server maxima per kind (`MAX_GENERATE_PER_DAY=50`, `MAX_DISCOVER_PER_DAY=30`, `MAX_EXPLAIN_PER_DAY=100`) plus per-user defaults (`DEFAULT_GENERATE_PER_DAY=20`, `DEFAULT_DISCOVER_PER_DAY=10`, `DEFAULT_EXPLAIN_PER_DAY=50`), all env-overridable + documented in `.env.example` (`# ── LLM cost guard (Phase 3) ──`).
      verify: `pytest tests/test_config.py::test_quota_ceilings_load` — values load from env and fall back to documented defaults. ✅
- [x] **3.2.2** `resolve_user_cap(user_id, kind)` (in new `app/quota.py`) reads the per-user value from `user_settings` (keys `daily_cap_generate`/`daily_cap_discover`/`daily_cap_explain` via `SettingsRepository`), then `min()`s it against the server maximum (a missing/blank/non-numeric setting uses the server default).
      verify: `pytest tests/quota/test_caps.py::test_user_cap_clamped` — a user-set cap above the server max resolves to the server max; an unset cap resolves to the default. ✅
- [x] **3.2.3** Daily-cap gate in `app/quota.py` (`enforce_daily_cap` / `QuotaGuard.check`): before an LLM call of `kind`, compare `get_user_daily_count(user_id, kind, today-UTC)` to `resolve_user_cap`; raise `DailyCapReached` → 429 with body `{code: "daily_cap_reached", kind}` when at/over (mapped by an app-level exception handler so the body is exactly that shape).
      verify: `pytest tests/quota/test_caps.py::test_daily_cap_blocks` — with cap=2 and count=2, the gate raises 429; with count=1 it allows and the call proceeds. ✅
      depends: 3.1.4
- [x] **3.2.4** Wire the gate into all LLM endpoints via the shared `app/quota.py` component: `/generate`, `/discover`, `/discover/accept` use the `quota_guard(kind)` **FastAPI dependency** (`/discover/accept` counts as `generate`); after a successful provider call each calls `QuotaGuard.record_success` to increment via `UsageRepository.increment_usage(current_user.id, kind, today)` on the privileged `get_usage_db` session. **Deviation (documented):** `/explain` is cache-aware — the guard is built `enforce=False` and the SAME gate runs **inside `ExplainService` after the cache lookup**, so a cache hit is free (no gate, no increment) and only a cache miss is gated + counted.
      verify: `pytest tests/api/test_quota_endpoints.py::test_each_kind_capped` — exhausting each endpoint's cap returns 429 for that endpoint only, others unaffected (covers all four routes + the explain cache-hit-is-free path). ✅

## 3.3 — Per-user sliding-window rate limiting  ·  S

_Context: caps are per-day; rate limiting smooths bursts (e.g. N requests/minute) so one user can't hammer the provider's RPM ceiling._

- [x] **3.3.1** Wired the limiter behind a small `RateLimiter` Protocol (keyed by `user_id`) in new `app/ratelimit.py`. **Decision (locked): in-process, NO new dependency** — an `InProcessRateLimiter` sliding-window-log with an **injectable clock** (default `time.monotonic`; tests fake it), exposed via the `get_rate_limiter()` dependency returning a process-wide singleton (overridable in tests). slowapi rejected (heavier, harder to fake the clock). The module docstring flags the **Phase-6 distributed (Postgres/Upstash) swap** (Cloud Run may scale >1 instance → in-process under-counts).
      verify: `pytest tests/quota/test_ratelimit.py::test_window_counts` — within one window the counter increments and resets after the window elapses (clock injected/faked). ✅
- [x] **3.3.2** Rate-limit gate in `QuotaGuard.check` running AFTER email and BEFORE the daily-cap gate; over the per-user `RATE_LIMIT_PER_MIN` (new env setting, default 10, documented in `.env.example`) it raises `RateLimited` → **429** with a `Retry-After` header (seconds until the window frees) and body `{code: "rate_limited"}`. Keyed by `user_id`, counting ALL gated kinds; the token is consumed once the request passes the email gate (even if the cap then blocks).
      verify: `pytest tests/quota/test_ratelimit.py::test_blocks_over_limit` — the (limit+1)th call within the window returns 429 with a `Retry-After` header; a later call after the window passes. ✅
- [x] **3.3.3** Gate ordering enforced in `QuotaGuard.check` exactly as 03-backend.md: **email-verified → rate-limit → daily-cap → global-budget** (the 3.4 global-budget slot is ordered but not built here), so the earliest failure surfaces.
      verify: `pytest tests/quota/test_gate_order.py::test_order` — a request failing email+rate+cap surfaces them in order as the gates are relaxed (403 `email_unverified` → 429 `rate_limited` → 429 `daily_cap_reached`). ✅

## 3.4 — Global daily budget kill-switch  ·  M

_Context: the backstop that guarantees "I will never get a bill" — a project-wide daily counter set safely below the active provider's free daily limit; once tripped, all LLM generation is refused for the rest of the day._

- [x] **3.4.1** Config `GLOBAL_DAILY_BUDGET` (project-wide call ceiling, default 1000) documented as "set below the active provider's free RPD"; loaded via `pydantic-settings`.
      verify: `pytest tests/test_config.py::test_global_budget_loads` passes; `.env.example` documents the var with a comment pointing at provider free-tier RPD. ✅
- [x] **3.4.2** Global-budget gate in `quota.py` as the LAST gate: when `get_budget_count(today) >= GLOBAL_DAILY_BUDGET` (read on the privileged `get_usage_db`/`UsageSession`), refuse with a friendly response (`{code: "daily_limit_reached", message: "Daily limit reached, please try again tomorrow."}`, **status 429** — 03-backend.md lists "503/429" without mandating 503, so 429 to match the other quota gates).
      verify: `pytest tests/quota/test_budget.py::test_kill_switch_trips` — with the counter at the ceiling, the gate returns the friendly daily-limit body; below it, the call is allowed. ✅
- [x] **3.4.3** Increment `llm_budget` (and `llm_usage`) only on a successful provider call, atomically (3.1.3), so blocked/failed/cache-hit calls don't burn budget (check-then-increment-on-success; `record_success` runs only after the provider returns).
      verify: `pytest tests/quota/test_budget.py::test_failed_call_no_increment` — a provider error leaves both counters unchanged; a success bumps both by exactly 1. ✅
- [x] **3.4.4** Integration test that trips the global kill-switch end-to-end: drive real HTTP `/generate` calls (provider = FakeLLM, zero real LLM calls) until the budget ceiling, then assert the next call across a *different* user also gets the friendly daily-limit response.
      verify: `pytest tests/integration/test_global_killswitch.py` passes — budget is global, not per-user. ✅
      depends: 3.4.2

## 3.5 — Concurrency cap & backoff honoring 429s  ·  S

_Context: even within caps, bound in-flight provider calls and back off on provider 429/5xx so we never amplify load against the free tier._

- [x] **3.5.1** Global concurrency limiter (asyncio semaphore sized by `LLM_MAX_CONCURRENCY`, default 4) around every provider call: `app/llm_runner.py` `LLMConcurrencyLimiter.run` offloads each blocking provider call to a worker thread (`asyncio.to_thread`) under a process-global semaphore (so the event loop stays responsive AND in-flight calls are bounded), exposed via the `get_llm_limiter()` singleton dependency (overridable in tests, `reset_llm_limiter()` rebuilds it) and threaded through `Generate`/`Discover`/`Explain` services. Over the limit a request waits briefly (bounded by `ACQUIRE_TIMEOUT_SECONDS`) then raises `ProviderBusy` → **503** `{"code":"server_busy","message":"The server is busy, please try again in a moment."}` (+ short `Retry-After`) rather than queuing unbounded. Documented in `.env.example` with the scale-out sequencing note (this cap bounds the kill-switch overshoot; multi-instance also needs the Phase-6 distributed rate limiter).
      verify: `pytest tests/quota/test_concurrency.py::test_semaphore_caps_inflight` — with concurrency=2 and a slow fake provider recording a thread-safe in-flight high-water-mark, at most 2 calls are in flight simultaneously. ✅
- [x] **3.5.2** Exponential backoff **with jitter** on provider 429/5xx in `lengua_core/llm/retry.py` `call_with_retry` (injectable `sleep` + injectable `rng` for deterministic-under-test full jitter: `base_delay*2**(n-1)*rng()`), capped at `max_attempts`. When transient errors persist across every attempt it raises a clean typed `LLMTransientError` (raw vendor error as `__cause__`) — mapped by an app-level handler to the same friendly **503** `server_busy` response, not an unhandled 500.
      verify: `pytest tests/llm/test_backoff.py::test_retries_then_gives_up` — a fake provider returning 429 three times triggers backoff sleeps (faked clock) and then a clean `LLMTransientError`, not an unhandled exception; an HTTP test proves it renders 503 `server_busy`. ✅

## 3.6 — Cost minimization  ·  S

_Context: cheapest call is the one you don't make; cap request size/output and reuse cached results so each allowed call costs the least possible tokens._

- [ ] **3.6.1** Enforce a max words-per-request on `/generate` (Pydantic validation, e.g. `MAX_WORDS_PER_REQUEST`) and a max output-token / max-tokens param passed to the provider.
      verify: `pytest tests/api/test_generate_limits.py::test_words_and_tokens_capped` — over-limit word lists 422; the provider call is invoked with the configured max-tokens.
- [ ] **3.6.2** Cache `word_explanations`: `/explain` returns the persisted explanation (from `cards.word_explanations` / a lookup) without an LLM call when one already exists for that word+language.
      verify: `pytest tests/api/test_explain_cache.py::test_cache_hit_skips_llm` — a second `/explain` for the same word makes zero provider calls and does not increment `gemini_usage`.
- [ ] **3.6.3** Reuse Discover results: a repeated `/discover` for the same language+topic within a short window returns the prior preview instead of a fresh LLM call.
      verify: `pytest tests/api/test_discover_reuse.py::test_repeat_reuses_preview` — the second identical discover call makes no provider call and returns the cached suggestions.

## 3.7 — Pre-call eligibility & abuse guard  ·  S

_Context: gate the gate — only verified accounts reach the LLM, with a light guard against signup-spam abuse of the shared key._

- [x] **3.7.1** Email-verified check as the FIRST gate in `QuotaGuard.check` (uses the verified-JWT `CurrentUser.email_verified`): an unverified caller is refused with `EmailUnverified` → **403** `{code: "email_unverified"}` before any rate limiter, counter, or provider is touched.
      verify: `pytest tests/quota/test_eligibility.py::test_unverified_blocked` — an unverified user calling `/generate` gets 403 `{code: "email_unverified"}` and no provider call happens. ✅
      depends: Phase 2 (email verification)
- [x] **3.7.2** Signup-abuse day-0 guard: a brand-new account (its `profiles.created_at` is on the current UTC day) gets a reduced first-day generate ceiling — effective generate cap = `min(resolve_user_cap(...,'generate'), NEW_ACCOUNT_DAY0_GENERATE_CAP)` (new env setting, default 5, documented in `.env.example`). Implemented as a clamp inside `enforce_daily_cap`'s generate path (reads `Profile.created_at` via `ProfilesRepository`); established accounts use the normal cap. A code comment notes where a CAPTCHA challenge would slot in (DESIGN-ONLY — not built). Generate-only for now (discover/explain could get their own day-0 caps later).
      verify: `pytest tests/quota/test_abuse_guard.py::test_new_account_cooldown` — an account created "today" hits the reduced first-day ceiling sooner than an established account. ✅

## 3.8 — Metrics & spans per LLM call  ·  S

_Context: observability threaded through the cost guard so budget burn and cap hits are visible before they become a problem (rolled up into Phase 5 dashboards)._

- [ ] **3.8.1** Emit an OTel span per LLM call with attributes: `llm.provider`, `llm.model`, `llm.latency_ms`, `llm.tokens_in/out`, `quota.kind`, `quota.cap_hit` (which gate, if any), `budget.remaining`.
      verify: `pytest tests/observability/test_llm_span.py::test_span_attributes` — an in-memory span exporter captures a span carrying all listed attributes for one fake call.
- [ ] **3.8.2** Counters/metrics: `llm_calls_total{kind,result}`, `llm_cap_hits_total{gate}`, and a `llm_budget_remaining` gauge updated after each accounted call.
      verify: `pytest tests/observability/test_llm_metrics.py::test_counters_and_gauge` — tripping a cap increments `llm_cap_hits_total` and the gauge reflects `GLOBAL_DAILY_BUDGET - budget_count`.

## 3.9 — BYOK key-resolution seam (design only)  ·  S

_Context: the growth escape hatch (see ../08-open-questions-and-costs.md) — make key resolution pluggable now so a user key could later override the operator key. DESIGN the seam; do NOT build BYOK._

- [x] **3.9.1** Introduced `resolve_llm_key(user)` in `lengua_core/llm/keys.py` — today always returns the operator key from env for the active provider (`GROQ_API_KEY`/`GEMINI_API_KEY` per `LLM_PROVIDER`); the `user` param is the inert future BYOK override point. Both `GroqProvider.from_env`/`GeminiProvider.from_env` now obtain the key ONLY through it (no module other than `keys.py` reads the key env vars). `get_provider()`/`from_env()` keep working.
      verify: `pytest tests/llm/test_key_resolution.py::test_operator_key_only` — the resolver returns the env operator key for any user (and `None`); a grep over `lengua_core/llm/*.py` confirms the key env-var names appear only in `keys.py` (the resolver). ✅
- [x] **3.9.2** Design note in `docs/byok-seam.md` (+ the `keys.py` module docstring) describing how a per-user key would plug into `resolve_llm_key` (branch on `user`/`profiles.plan`) and how the caps/budget gates would SKIP a BYOK user later — DESIGN ONLY.
      verify: the note exists and references the resolver + `profiles.plan`; no BYOK storage/UI/columns were added (no new migrations, no settings UI, no per-user key branching beyond the inert `user` param). ✅

---

## Phase 3 exit gate

Phase 3 is DONE only when all of these hold:

- [ ] Per-user daily caps enforced for generate/discover/explain, clamped by server maxima — verify: `pytest tests/quota/test_caps.py` green; manual: a user at their cap gets 429 `daily_cap_reached`.
- [ ] Per-user sliding-window rate limit enforced in correct gate order — verify: `pytest tests/quota/test_ratelimit.py tests/quota/test_gate_order.py` green.
- [ ] Global daily kill-switch trips project-wide and returns the friendly daily-limit message — verify: `pytest tests/integration/test_global_killswitch.py` green (a second user is also refused once the budget is spent).
- [ ] Counters increment only on successful provider calls and atomically — verify: `pytest tests/repositories/test_usage_repo.py tests/quota/test_budget.py::test_failed_call_no_increment` green.
- [ ] Verified email required and a signup-abuse guard active before any LLM call — verify: `pytest tests/quota/test_eligibility.py tests/quota/test_abuse_guard.py` green.
- [ ] Load test proves caps/limits/budget hold with **zero paid usage** — verify: a small Locust/k6 (or pytest async) load run against the API with the provider faked drives sustained traffic; assert no request exceeds caps, the global guard trips at the ceiling, and the real operator key is never invoked (provider faked / call count bounded by budget).
- [ ] Every LLM call emits a span + metrics with cap-hit and budget-left — verify: `pytest tests/observability/test_llm_span.py tests/observability/test_llm_metrics.py` green.
- [ ] BYOK seam exists as a pluggable resolver with a design note, no BYOK feature built — verify: `pytest tests/llm/test_key_resolution.py` green and the design note is present.
- [ ] every task above merged via a green PR with the quality gate held (≥80% coverage, E2E)
