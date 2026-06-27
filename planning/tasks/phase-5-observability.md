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

- [ ] **5.2.1** Add custom spans `gemini.generate` / `gemini.discover` / `gemini.explain` with attributes: `model`, input size, output tokens, latency, retry count, and **which quota gate (if any) blocked** the call.
      verify: `pytest apps/api/tests/test_llm_spans.py` runs each LLM operation against the fake and asserts the span name, `model`, token, and `quota.gate_blocked` attributes are recorded.
- [ ] **5.2.2** Add a `review.grade` span carrying rating, FSRS reschedule result, and proficiency delta.
      verify: `pytest apps/api/tests/test_review_span.py` grades a card and asserts the `review.grade` span exists with `rating`, `next_due`, and `proficiency_delta` attributes.
- [ ] **5.2.3** Add a `quota.check` span carrying per-user cap state and global budget remaining.
      verify: `pytest apps/api/tests/test_quota_span.py` asserts a `quota.check` span with `user.cap_remaining` and `budget.remaining` attributes is emitted on every gated call.
      depends: Phase 3 cost guard
- [ ] **5.2.4** Define and emit the cost/LLM counters and gauges: `gemini_calls_total{kind}`, `gemini_tokens_total`, `gemini_budget_remaining`, `quota_blocks_total{reason}`.
      verify: `pytest apps/api/tests/test_cost_metrics.py` drives a generate + a quota block and asserts `gemini_calls_total{kind="generate"}` incremented, `gemini_budget_remaining` decreased, and `quota_blocks_total{reason=...}` incremented.
      depends: 5.2.3
- [ ] **5.2.5** Define and emit the product counters/gauges: `reviews_total`, `cards_created_total`, `signups_total`, `active_users`.
      verify: `pytest apps/api/tests/test_product_metrics.py` performs a signup, card creation, and review and asserts each counter incremented; `active_users` reflects the distinct user.
- [ ] **5.2.6** Confirm RED metrics (request rate, error rate, p50/p95/p99 duration) are exported per route from the FastAPI instrumentation and queryable in Prometheus/Mimir.
      verify: in Grafana Explore against Mimir, a query for the request-duration histogram returns a per-route p95 series after generating traffic with a small load script.
      depends: 5.1.5

## 5.3 — Structured, correlated logging  ·  S

_Context: logs only earn their keep if they join to traces — every line carries `trace_id` + `span_id` + `user_id`._

- [ ] **5.3.1** Switch stdlib `logging` to a structured JSON formatter and route it through OTel so each log record is exported to Loki.
      verify: run the API, make a request, and confirm the emitted log line is valid JSON (parses with `python -m json.tool`) and appears in Grafana Loki filtered by `service_name="lengua-api"`.
- [ ] **5.3.2** Inject `trace_id` + `span_id` + `user_id` into every log record via an OTel/log-context processor.
      verify: `pytest apps/api/tests/test_log_correlation.py` captures a log emitted inside a request and asserts the record's `trace_id`/`span_id` equal the active span's and `user_id` matches `current_user`.
- [ ] **5.3.3** Verify end-to-end log↔trace correlation in Grafana: from one request, jump from its Tempo trace to the Loki logs sharing that `trace_id`.
      verify: in Grafana, open a trace from one request and use the Tempo→Loki "trace to logs" link to land on log lines whose `trace_id` matches the trace.
      depends: 5.1.5, 5.3.2

## 5.4 — Error tracking (Sentry)  ·  S

_Context: backend and web get **separate DSNs**; Sentry issues link to Grafana traces via shared `trace_id`._

- [ ] **5.4.1** Add the Sentry SDK to the FastAPI backend with its own DSN, capturing exceptions plus request/user tags and the OTel `trace_id`.
      verify: hit a deliberately failing test endpoint; the exception appears as a Sentry issue tagged with the `user_id` and a `trace_id` that resolves to a Grafana Tempo trace.
- [ ] **5.4.2** Add the Sentry browser SDK to `apps/web` with a **separate** DSN, capturing JS errors + web vitals/performance.
      verify: trigger a thrown error in the web app (a hidden debug button); a JS error event with web-vitals context shows up under the web project's DSN in Sentry (covered by a Playwright step that asserts the Sentry capture call fired).
- [ ] **5.4.3** Configure a Sentry alert rule for a new/regressed issue or error-volume spike routed to the team channel.
      verify: triggering the test error from 5.4.1 produces a Sentry notification in the configured channel (Slack/Discord/email).

## 5.5 — Frontend trace propagation  ·  S

_Context: so a user action's trace continues from the browser into the API (the client→API leg of the correlation checklist)._

- [ ] **5.5.1** Add OTel browser tracing (or W3C `traceparent` propagation) to the web app's fetch/Query client so each API request carries a `traceparent` header continuing the client span.
      verify: in browser devtools (or a Playwright network assertion) an API request shows an outgoing `traceparent` header; in Grafana Tempo that request's trace begins with a browser/client span as the root.
- [ ] **5.5.2** Confirm one user action yields a single end-to-end trace spanning client→API→DB and/or LLM.
      verify: a Playwright run of "generate one sentence" yields a trace in Tempo containing, in one trace id, a client span → FastAPI server span → SQLAlchemy span → provider httpx/`gemini.generate` span.
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
