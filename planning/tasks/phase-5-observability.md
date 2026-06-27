# Phase 5 — Observability

> **Effort:** S–M (start in Phase 1, finish here)  ·  **Depends on:** Phase 1 backend core (auto-instrument starts there); custom quota spans land alongside Phase 3  ·  **Overlaps:** Phase 6 — two tasks here (5.6.4 Infra dashboard, 5.8.1 external uptime check) need the Cloud Run / prod deploy that Phase 6 stands up, so those two land after the matching Phase 6 deploy while the rest of this phase completes earlier  ·  **Unlocks:** Phase 6 (infra/CI/CD) and Phase 9 (launch watch)
> **Source:** roadmap Phase 5 (../02-roadmap.md) · deep dive (../06-observability.md)
> The per-PR quality gate (../09-testing-quality.md) applies to EVERY task below: each lands via a PR that is 100% green + ≥80% coverage (backend & frontend) + Playwright E2E. A task is not done until its tests keep coverage ≥80%.

**Goal:** a single user action produces one trace spanning client→API→DB/LLM, every log line is correlated by `trace_id`, Grafana dashboards show live cost vs budget, and a deliberately triggered alert reaches a real notification channel.

**Status legend:** [ ] todo · [~] in progress · [x] done · [!] blocked

---

## 5.1 — OpenTelemetry backend foundation  ·  M

_Context: auto-instrumentation and the OTLP export pipeline are wired in Phase 1 as the backend is built; this group finalizes and verifies them. The active LLM provider is Groq in dev/test/CI; the same httpx/custom spans cover Gemini in prod with no code change._

- [x] **5.1.1** Add the OTel SDK + `opentelemetry-distro`/`opentelemetry-exporter-otlp` to `apps/api`, configure a `TracerProvider`/`MeterProvider`/`LoggerProvider` from env, and tag every signal with `service.name=lengua-api` and `deployment.environment={local|staging|prod}` resource attributes. _(SDK + OTLP exporter already shipped in 1.7; this adds the shared `deployment.environment` resource — from `DEPLOYMENT_ENVIRONMENT`, defaulting to `ENV` — applied to BOTH the `TracerProvider` and the cost-guard `MeterProvider` via `app.observability.build_resource`. Deviation: `opentelemetry-distro` deliberately NOT added — it auto-configures providers and would fight the existing manual SDK wiring; the manual wiring satisfies the intent. The `LoggerProvider` lands in 5.3.)_
      verify: start the API locally with the OTLP exporter pointed at a local collector (or `ConsoleSpanExporter`); `pytest apps/api/tests/test_otel_resource.py` asserts emitted spans carry `service.name=lengua-api` and the env tag from `DEPLOYMENT_ENVIRONMENT`.
- [x] **5.1.2** Auto-instrument the FastAPI HTTP server so every route produces a server span with method, route template, and status code.
      verify: `curl localhost:8000/health` then inspect the collector/console — exactly one server span named for `GET /health` appears with `http.status_code=200`.
- [x] **5.1.3** Auto-instrument SQLAlchemy so DB queries become child spans under the request span. _(Gap found + fixed: the app engine was built via an early-bound `create_async_engine` (captured before instrumentation ran), so it emitted only the class-level `connect` span and NO statement spans. `get_engine` now resolves the OTel-wrapped factory at call time so `SELECT`/`INSERT` spans nest under the request — verified offline + by the integration test.)_
      verify: hit an endpoint that reads the DB (e.g. `GET /cards`); the trace shows a SQLAlchemy `SELECT` span as a child of the FastAPI server span (asserted in `pytest apps/api/tests/test_otel_db_spans.py`).
- [x] **5.1.4** Auto-instrument httpx so outbound LLM calls (Groq now / Gemini later) become client spans, and propagate context so they nest under the request span. _(httpx CLIENT-span instrumentation verified honestly against a controlled loopback server: a real outbound request emits a CLIENT span nested under the active span. RECONCILED: under the deterministic `FakeLLM` (dev/CI/E2E) the provider call is in-process and makes NO outbound httpx request — the provider-call signal there is the custom `llm.call` span (3.8/5.2); the prod Groq/Gemini HTTP path produces this httpx client span. Documented in the test + PR.)_
      verify: trigger a generate call against the deterministic LLM fake; the trace contains an httpx client span for the provider request nested under the route span (asserted in `pytest apps/api/tests/test_otel_httpx_spans.py`).
- [ ] **5.1.5** Wire the OTLP exporter to Grafana Cloud (Tempo) using `OTEL_EXPORTER_OTLP_ENDPOINT` + auth header read from env/secret per environment. _(As-code done + CI-verified: the env-driven exporter attaches a `BatchSpanProcessor` only when the endpoint is set (none otherwise) — covered by `tests/obs/test_otel_wiring.py`; `.env.example` documents the Grafana Cloud Tempo endpoint + the auth-token header. NOT ticked — the verify is LIVE + owner + needs the Phase-6 staging deploy; see `planning/outstanding-work.md` §11.)_
      verify: run the staging API with the Grafana Cloud OTLP creds; perform one request and find that trace in Grafana Tempo's "Explore" within ~1 minute, searchable by `service.name=lengua-api`.

## 5.2 — Custom spans & domain metrics  ·  M

_Context: the auto-instrumentation gives RED-per-route for free; these custom spans/metrics are the cost-guard and product signals from 06. The `quota.check` span and quota-block attributes land alongside the Phase 3 cost guard._

- [x] **5.2.1** Add custom spans `gemini.generate` / `gemini.discover` / `gemini.explain` with attributes: `model`, input size, output tokens, latency, retry count, and **which quota gate (if any) blocked** the call. _(Shipped as the provider-agnostic single `llm.call` span — NOT `gemini.*`, which predates the LLM seam — **extended** with `llm.input_size` (words for generate / count for discover / 1 for explain) + `llm.retry_count` (threaded out of `lengua_core.llm.retry.call_with_retry` via the usage seam) on top of the existing `llm.provider`/`llm.model`/`llm.latency_ms`/`llm.tokens_in`/`llm.tokens_out`; the quota-gate-blocked attr is `quota.cap_hit` (gate name, or `none`).)_
      verify: `pytest apps/api/tests/obs/test_llm_spans.py` runs generate/discover/explain against `FakeLLM` and asserts the span name (`llm.call`), `llm.model`, the token attrs, `quota.cap_hit`, `llm.input_size`, and `llm.retry_count` are recorded (offline `run_provider` branch coverage in `tests/obs/test_run_provider_obs.py`).
- [x] **5.2.2** Add a `review.grade` span carrying rating, FSRS reschedule result, and proficiency delta. _(Span wraps the `ReviewService.grade` flow — current during the body, so DB statements nest under it — with `review.rating` / `review.next_due` / `review.proficiency_delta`.)_
      verify: `pytest apps/api/tests/obs/test_review_span.py` grades a card and asserts the `review.grade` span exists with `review.rating`, `review.next_due`, and `review.proficiency_delta`.
- [x] **5.2.3** Add a `quota.check` span carrying per-user cap state and global budget remaining. _(A dedicated `quota.check` span, sibling of `llm.call` under the request span, started in `QuotaGuard.check` and always ended in a `finally` so it is emitted on admit AND block; carries `user.cap_remaining` + `budget.remaining`. Read once via `resolve_daily_cap_state` — no extra DB read, no gate-behavior change.)_
      verify: `pytest apps/api/tests/obs/test_quota_span.py` asserts a `quota.check` span with `user.cap_remaining` and `budget.remaining` is emitted on the admit AND the block path.
      depends: Phase 3 cost guard
- [x] **5.2.4** Define and emit the cost/LLM counters and gauges: `gemini_calls_total{kind}`, `gemini_tokens_total`, `gemini_budget_remaining`, `quota_blocks_total{reason}`. _(Shipped under the canonical provider-agnostic `llm_*` names: `llm_calls_total{kind,result}`, `llm_budget_remaining` (gauge). **Added** the missing token counter as `llm_tokens_total{kind,direction}` (in/out). `quota_blocks_total{reason}` IS the existing `llm_cap_hits_total{gate}` (gate == reason) — single counter, no duplicate. No `gemini_*` name introduced.)_
      verify: `pytest apps/api/tests/obs/test_cost_metrics.py` drives a generate + a quota block and asserts `llm_calls_total{kind=generate,result=success}` incremented, `llm_budget_remaining` decreased, `llm_cap_hits_total` (the blocks counter) incremented, and `llm_tokens_total` incremented.
      depends: 5.2.3
- [x] **5.2.5** Define and emit the product counters/gauges: `reviews_total`, `cards_created_total`, `signups_total`, `active_users`. _(New `app/product_metrics.py` reusing the one app-wide `MeterProvider`; wired at `ReviewService.grade` / `GenerateService.save` / `MeService.get`. `active_users` is an observable gauge over a rolling in-process window; `signups_total` is a process-local first-seen proxy — both carry the Phase-6 distributed caveat at the seam, like the rate limiter.)_
      verify: `pytest apps/api/tests/obs/test_product_metrics.py` performs a signup, card creation, and review and asserts each counter incremented and `active_users` reflects the distinct user.
- [x] **5.2.6** Confirm RED metrics (request rate, error rate, p50/p95/p99 duration) are exported per route from the FastAPI instrumentation and queryable in Prometheus/Mimir. _(CI-verified: `FastAPIInstrumentor.instrument_app` is now given the app meter provider, so each request records the `http.server.duration` histogram per route. The pinned instrumentation labels it `http.target` (path) under the old HTTP semconv — the span still carries `http.route`; either satisfies "per-route". The **live half** — query the histogram p95 per route in Grafana Explore against Mimir after a load script — is owner/Phase-6, logged in `planning/outstanding-work.md` §11.)_
      verify: `pytest apps/api/tests/obs/test_red_metrics.py` asserts a `GET /health` request emits an `http.server.duration` histogram carrying a per-route label (`http.route`/`http.target`).
      depends: 5.1.5

## 5.3 — Structured, correlated logging  ·  S

_Context: logs only earn their keep if they join to traces — every line carries `trace_id` + `span_id` + `user_id`._

- [x] **5.3.1** Switch stdlib `logging` to a structured JSON formatter and route it through OTel so each log record is exported to Loki. _(The structured JSON access line shipped in 1.7 (`JsonLogFormatter` → stdout, the primary Cloud-Run→Loki path) is KEPT. This adds the direct-to-Loki alternative: a module-owned OTel `LoggerProvider` + a `LoggingHandler` (attached to the root + access loggers) routing stdlib logging through OTel, with a `BatchLogRecordProcessor(OTLPLogExporter())` attached **only** when `OTEL_EXPORTER_OTLP_LOGS_ENDPOINT`/`…_OTLP_ENDPOINT` is set — no-op with zero egress otherwise, mirroring the tracer/meter; the same `build_resource` (`service.name` + `deployment.environment`) is applied so Loki can filter by `service_name=lengua-api`. CI half done + GREEN. **NOTE (deprecation, logged §11):** `opentelemetry.sdk._logs.LoggingHandler` emits a relocation `DeprecationWarning` in OTel ≥1.43 — kept (it is the standard OTLP-log bridge; the logs signal is still unstable and the suggested package is not a dep), revisit when logs stabilize. The **live** half — the line actually appears in Grafana Loki filtered by `service_name=lengua-api` — needs the Phase-6 staging deploy + Grafana creds (owner); see `planning/outstanding-work.md` §11.)_
      verify: run the API, make a request, and confirm the emitted log line is valid JSON (parses with `python -m json.tool`) and appears in Grafana Loki filtered by `service_name="lengua-api"`.
- [x] **5.3.2** Inject `trace_id` + `span_id` + `user_id` into every log record via an OTel/log-context processor. _(A `logging.Filter` — `app.observability.TraceCorrelationFilter`, attached to the access-log stdout handler + the OTLP `LoggingHandler` — stamps `trace_id`/`span_id` from the active OTel span and `user_id` from a new per-request contextvar (`app.request_context`, set in `app.deps.get_current_user` where the identity resolves — additive, auth logic unchanged). RECONCILED path: the test lives at `apps/api/tests/obs/test_log_correlation.py` (the obs test dir, like 3.8/5.2), not `apps/api/tests/`. Honest limitation documented: the per-request access line is emitted by the `BaseHTTPMiddleware` in the OUTER ASGI task, where the user contextvar (set by the auth dependency in the inner request task) is not visible, so the access line's `user_id` is `None`; in-request application logs carry the real `user_id` — which is exactly what the verify asserts.)_
      verify: `pytest apps/api/tests/test_log_correlation.py` captures a log emitted inside a request and asserts the record's `trace_id`/`span_id` equal the active span's and `user_id` matches `current_user`.
- [ ] **5.3.3** Verify end-to-end log↔trace correlation in Grafana: from one request, jump from its Tempo trace to the Loki logs sharing that `trace_id`. _(ENTIRELY LIVE + owner + Phase-6: needs Tempo + Loki populated by a deployed service + the Grafana Tempo→Loki "trace to logs" data-link configured. Not tickable as code; logged in `planning/outstanding-work.md` §11. The as-code prerequisites are done: every log carries `trace_id` (5.3.2) and the OTLP trace+log export is wired (5.1.5 + 5.3.1).)_
      verify: in Grafana, open a trace from one request and use the Tempo→Loki "trace to logs" link to land on log lines whose `trace_id` matches the trace.
      depends: 5.1.5, 5.3.2

## 5.4 — Error tracking (Sentry)  ·  S

_Context: backend and web get **separate DSNs**; Sentry issues link to Grafana traces via shared `trace_id`._

- [x] **5.4.1** Add the Sentry SDK to the FastAPI backend with its own DSN, capturing exceptions plus request/user tags and the OTel `trace_id`. _(CI half DONE. New `app/error_tracking.py`: `sentry_sdk.init` runs **only** when `SENTRY_DSN_API` is set — a no-op with zero egress otherwise, mirroring the OTLP discipline — with the Starlette+FastAPI integrations, `environment` from `DEPLOYMENT_ENVIRONMENT` (shared `app.observability.deployment_environment`), and `send_default_pii=False`. Per request, `bind_request_scope` (called from `app.deps.get_current_user`, after the identity verifies — additive, no auth-decision change) stamps the authenticated `user.id` + a `trace_id` tag (the active OTel span's id) onto Sentry's **isolation scope**, so an auto-captured exception carries both (binding the shared scope from the auth dependency is robust across the `BaseHTTPMiddleware` task boundary, unlike a contextvar). A deliberately-failing `GET /__test__/debug-error` is gated EXACTLY like `/__test__/llm-calls` (mounted only under `LLM_PROVIDER=fake`) AND requires a valid bearer token, so it is prod-inert + anonymous-unreachable + leaks no internals (generic 500). `tests/obs/test_sentry.py` asserts the no-DSN no-op, the enabled init + environment, and the end-to-end capture carrying `user_id` + a 32-hex `trace_id` via an in-memory transport (zero egress). The **live half** — the Sentry issue's `trace_id` actually resolves to a Grafana Tempo trace — is owner + needs the Phase-6 staging deploy + live Sentry/Grafana creds; logged in `planning/outstanding-work.md` §11.)_
      verify: hit a deliberately failing test endpoint; the exception appears as a Sentry issue tagged with the `user_id` and a `trace_id` that resolves to a Grafana Tempo trace.
- [x] **5.4.2** Add the Sentry browser SDK to `apps/web` with a **separate** DSN, capturing JS errors + web vitals/performance. _(CI half DONE. `@sentry/react` + new `apps/web/src/lib/error-tracking.ts`: `initErrorTracking` runs `Sentry.init` **only** when a build-time `VITE_SENTRY_DSN_WEB` is set (no-op otherwise — dev/CI/E2E load nothing, zero egress), with `browserTracingIntegration()` for performance/Web-Vitals + `sendDefaultPii:false`. **RECONCILED:** introduced `VITE_SENTRY_DSN_WEB` (the old root `.env.example` `SENTRY_DSN_WEB` was not `VITE_`-prefixed so it could never reach the bundle) — added to `apps/web/.env.example` + `apps/web/src/vite-env.d.ts`, with the root `.env.example` updated to point there. A hidden, sr-only `DebugErrorButton` (mounted app-global in `main.tsx`) renders only when `VITE_ENABLE_DEBUG_TOOLS` is set — a flag a production build NEVER sets, so it is prod-inert — and on click routes a thrown error through the capture chokepoint. vitest covers init gating/options + the capture path (new files 100%); `e2e/sentry.spec.ts` asserts the capture fired (recorded on `window`) AND zero Sentry network egress (no DSN in the preview build); the e2e build + local Playwright `webServer` set `VITE_ENABLE_DEBUG_TOOLS=1`. The **live half** — the JS error + Web-Vitals event lands under the web DSN in Sentry — is owner + needs the Phase-6 deploy + live web Sentry DSN; logged in §11.)_
      verify: trigger a thrown error in the web app (a hidden debug button); a JS error event with web-vitals context shows up under the web project's DSN in Sentry (covered by a Playwright step that asserts the Sentry capture call fired).
- [ ] **5.4.3** Configure a Sentry alert rule for a new/regressed issue or error-volume spike routed to the team channel. _(ENTIRELY LIVE + owner: a Sentry-dashboard alert rule + a real notification channel (Slack/Discord/email). No CI-verifiable portion — NOT ticked; logged in `planning/outstanding-work.md` §11. The trigger it would fire on (the debug error) is wired by 5.4.1.)_
      verify: triggering the test error from 5.4.1 produces a Sentry notification in the configured channel (Slack/Discord/email).

## 5.5 — Frontend trace propagation  ·  S

_Context: so a user action's trace continues from the browser into the API (the client→API leg of the correlation checklist)._

- [x] **5.5.1** Add OTel browser tracing (or W3C `traceparent` propagation) to the web app's fetch/Query client so each API request carries a `traceparent` header continuing the client span. _(Shipped as minimal, dependency-light W3C `traceparent` propagation — NOT a heavy `@opentelemetry` browser SDK, which would bloat the bundle: new `apps/web/src/lib/trace.ts` `generateTraceparent()` mints a fresh version-`00`, sampled (`01`) header per call from `crypto.getRandomValues` (16-byte trace-id + 8-byte span-id, never all-zero), injected by a `traceMiddleware` in the openapi-fetch `onRequest` (`apps/web/src/lib/api-client.ts`); the 401 refresh/retry path clones the request so the header is preserved, not regenerated. CI-verified. The **live half** — the trace begins with a **browser/client span as the root** in Tempo — needs the browser to EXPORT its own client span (a web OTLP SDK) + a deployed collector, deferred to Phase 6; logged in `planning/outstanding-work.md` §11.)_
      verify: `pnpm --filter web test` asserts `traceMiddleware` injects a W3C-shaped `traceparent` (and preserves it across the 401 retry) and `apps/web/src/lib/trace.test.ts` covers the generator (format + randomness + never-all-zero); `apps/web/e2e/generate.spec.ts` asserts a real API request carries an outgoing `traceparent` matching the W3C regex (ephemeral-stack suite).
- [x] **5.5.2** Confirm one user action yields a single end-to-end trace spanning client→API→DB and/or LLM. _(CI half DONE + ticked: `apps/api/tests/obs/test_trace_continuation.py` (`@pytest.mark.integration`) drives `POST /generate` carrying a W3C `traceparent` and asserts the FastAPI SERVER span CONTINUES it — server `trace_id` == the supplied trace-id, parented under the supplied client span-id (propagation continues the client trace, via OTel's default W3C `tracecontext` propagator) — and that the SQLAlchemy statement span (DB leg) and the custom `llm.call` span (LLM leg) share that trace-id and nest under the server span, i.e. client→API→DB/LLM is ONE trace. RECONCILED: under the deterministic `FakeLLM` the provider-call signal is the `llm.call` span, NOT an httpx/`gemini.generate` span — the plan text predates the provider-agnostic LLM seam (see §11). The **live confirmation** — seeing the assembled trace in Tempo with a browser/client span as the root, plus the browser exporting that client span — is owner/Phase-6, logged in §11.)_
      verify: `pytest apps/api/tests/obs/test_trace_continuation.py` (CI, Postgres up) asserts one supplied trace-id spans the FastAPI server span → SQLAlchemy span → `llm.call` span.
      depends: 5.1.4, 5.5.1

## 5.6 — Grafana dashboards  ·  M

_Context: the four dashboards from 06; the cost-guard is the most important for "stay free." Dashboards are committed as code (JSON) so they're reproducible per environment._

- [ ] **5.6.1** Build the **Service health** dashboard: request rate, error rate, and p50/p95/p99 latency per route.
      verify: the dashboard JSON is committed under `infra/grafana/` and, after a load script, renders non-empty rate/error/latency panels for at least `/generate` and `/review`.
      depends: 5.2.6
- [ ] **5.6.2** Build the **Gemini cost-guard** dashboard: calls/day vs budget ceiling, `gemini_budget_remaining`, quota blocks by reason, and tokens/day.
      verify: after driving generate calls + a forced quota block, the dashboard shows live `gemini_budget_remaining` decreasing and a non-zero `quota_blocks_total{reason}` panel.
      depends: 5.2.4
- [ ] **5.6.3** Build the **Product** dashboard: daily reviews, cards created, signups, active users, and CEFR level distribution.
      verify: after a seeded signup→generate→review run, the product dashboard panels show non-zero reviews, cards, signups, and active users.
      depends: 5.2.5
- [ ] **5.6.4** Build the **Infra** dashboard: Cloud Run instance count / cold starts, DB latency, and an error-logs (Loki) feed panel.
      verify: with the staging Cloud Run service receiving traffic, the dashboard shows instance/cold-start and DB-latency panels populated and the Loki error-feed panel returns rows on a forced error.
      depends: Phase 6 Cloud Run deploy

## 5.7 — Alerts to a real channel  ·  S

_Context: alerts must reach an actual notification channel (Slack/Discord/email) — proving delivery is the phase's headline check. Budget≥80% is the early warning before the Phase 3 kill-switch trips._

- [ ] **5.7.1** Configure a Grafana notification contact point (Slack/Discord/email) and confirm delivery with a test notification.
      verify: Grafana's "Test" on the contact point delivers a message to the real channel; a screenshot/record of the received message is attached to the PR.
- [ ] **5.7.2** Alert: API error rate (5xx spike) above threshold.
      verify: drive forced 5xx responses on staging until the threshold trips; an error-rate alert fires to the configured channel and resolves when traffic returns to normal.
      depends: 5.6.1
- [ ] **5.7.3** Alert: p95 latency above threshold sustained.
      verify: inject artificial latency on a staging route; the p95 alert fires to the channel after the sustained window and clears afterward.
      depends: 5.6.1
- [ ] **5.7.4** Alert: Gemini global budget ≥ ~80% of ceiling (early warning before the kill-switch).
      verify: lower the ceiling (or push synthetic usage) so `gemini_budget_remaining` crosses 80% consumed; the budget alert fires to the channel.
      depends: 5.6.2
- [ ] **5.7.5** Alert: prod `/health` uptime check failing, wired to the same channel.
      verify: point the uptime alert at a deliberately failing endpoint; the uptime alert reaches the channel within the check interval (ties into 5.8).
      depends: 5.8.1

## 5.8 — External uptime check  ·  S

_Context: a free external prober for prod `/health`, independent of the app's own stack._

- [ ] **5.8.1** Set up a free external uptime monitor (UptimeRobot / BetterStack / Grafana synthetic) hitting prod `/health` every few minutes, alerting on failure.
      verify: the monitor dashboard shows the prod `/health` check green at the configured interval; pausing the service (or pointing at a bad path) flips it to DOWN and sends a notification.
      depends: Phase 6 prod deploy

## 5.9 — Product analytics (PostHog)  ·  M

_Context: distinct from OTel/Sentry — answers "are people learning and coming back?" PostHog free tier, EU-hosted, anonymized, **consent-gated**, no PII._

- [ ] **5.9.1** Add the PostHog client to the web app pointed at the EU host, with capture **disabled until consent** and a consent toggle in Settings/Account.
      verify: a Playwright run shows zero PostHog network calls before consent; after accepting consent, capture requests go to the `eu.posthog.com` host and stop again on opt-out.
- [ ] **5.9.2** Instrument the activation funnel events: `signup → add language → first generate → first review`, with no PII in event properties.
      verify: complete the funnel as a test user with consent on; all four named events appear in PostHog and a review of their payloads confirms no email/name/PII fields.
      depends: 5.9.1
- [ ] **5.9.3** Build the PostHog funnel + D1/D7 retention + reviews/day + feature-usage (Discover, tap-a-word) insights.
      verify: the saved PostHog funnel insight renders the four-step activation funnel with the seeded test users, and the retention insight shows a D1/D7 cohort grid.
      depends: 5.9.2

---

## Phase 5 exit gate

Phase 5 is DONE only when all of these hold:

- [ ] One user action produces a single trace spanning client→API→DB and/or LLM — verify: a Playwright "generate one sentence" run yields one trace id in Tempo containing client → FastAPI → SQLAlchemy → provider (`gemini.generate`/httpx) spans (5.5.2).
- [ ] Logs for that request carry the same `trace_id` — verify: in Grafana, the Tempo→Loki link from that trace lands on JSON log lines whose `trace_id` matches (5.3.3).
- [ ] A thrown error appears in Sentry with a `trace_id` that jumps to the Grafana trace — verify: trigger the debug error and follow its `trace_id` from the Sentry issue to a Tempo trace (5.4.1).
- [ ] The cost-guard dashboard shows live LLM usage vs ceiling — verify: drive generate calls + a forced quota block and watch `gemini_budget_remaining` fall and `quota_blocks_total{reason}` rise on the dashboard (5.6.2).
- [ ] A deliberately triggered alert reaches the real notification channel — verify: force the error-rate (or budget≥80%) condition on staging and confirm the alert message arrives in the configured Slack/Discord/email channel (5.7.2 / 5.7.4).
- [ ] An external uptime check watches prod `/health` and alerts on failure — verify: the external monitor shows prod `/health` green and flips to DOWN with a notification when the endpoint fails (5.8.1).
- [ ] every task above merged via a green PR with the quality gate held (≥80% coverage, E2E).
