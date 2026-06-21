# 06 — Observability (OpenTelemetry, logs, traces, metrics)

Goal: every request is traceable end-to-end, logs are correlated, key metrics are dashboarded,
and real alerts fire — all on free tiers. **Instrument as you build (from Phase 1), don't bolt
it on at the end.**

## Backend signals (OpenTelemetry)

- **Traces** — auto-instrument FastAPI (HTTP server), SQLAlchemy (DB queries), and httpx (the
  Gemini calls). Add **custom spans** for the things we care about:
  - `gemini.generate` / `gemini.discover` / `gemini.explain` — attrs: model, input size,
    output tokens, latency, retry count, **which quota gate (if any) blocked it**.
  - `review.grade` — rating, FSRS reschedule, proficiency delta.
  - `quota.check` — per-user cap state, global budget remaining.
- **Metrics** — RED (Rate, Errors, Duration) per route, plus product/cost metrics:
  - `gemini_calls_total{kind}`, `gemini_tokens_total`, `gemini_budget_remaining`,
    `quota_blocks_total{reason}`.
  - `reviews_total`, `cards_created_total`, `signups_total`, `active_users`.
- **Logs** — **structured JSON**, every line carrying `trace_id` + `span_id` + `user_id` so
  logs join to traces. Route stdlib `logging` through OTel.

Exporter: **OTLP → Grafana Cloud** (Tempo = traces, Loki = logs, Prometheus/Mimir = metrics).
Set `OTEL_EXPORTER_OTLP_ENDPOINT` + auth header per environment; tag every signal with
`service.name=lengua-api` and `deployment.environment={local|staging|prod}`.

## Error tracking — Sentry

- **Backend**: Sentry SDK captures exceptions with trace context + request/user tags.
- **Web**: Sentry browser SDK (errors + performance + optional session replay) — separate DSN.
- **Mobile**: Sentry Capacitor SDK once the apps exist.
- Link Sentry issues to Grafana traces via shared `trace_id` where possible.

## Frontend / mobile telemetry

- **Web vitals** + JS errors via Sentry; optionally OTel browser tracing so a user action's
  trace continues into the API (propagate `traceparent` on fetch).
- Mobile: same web SDK inside the webview + Sentry Capacitor for native crashes.

## Dashboards (Grafana)

1. **Service health** — request rate, error rate, p50/p95/p99 latency per route.
2. **Gemini cost guard** — calls/day vs the budget ceiling, `gemini_budget_remaining`, quota
   blocks by reason, tokens/day. *(The most important dashboard for "stay free.")*
3. **Product** — daily reviews, cards created, signups, active users, level distribution.
4. **Infra** — Cloud Run instances/cold starts, DB latency, error logs feed.

## Alerts (to email / Slack / Discord)

- API error rate > threshold (e.g. 5xx spike).
- p95 latency > threshold sustained.
- **Gemini global budget ≥ ~80% of ceiling** (early warning before the kill-switch trips).
- Uptime check failing (prod `/health`).
- Sentry: new/regressed issue, or error volume spike.

## Uptime

- Free external check (UptimeRobot / BetterStack / Grafana synthetic) hitting prod `/health`
  every few minutes; alert on failure.

## Product analytics (PostHog)

Distinct from OTel/Sentry (which answer "is it healthy?"), product analytics answers "are
people learning and coming back?":

- **PostHog free tier**, EU-hosted, anonymized, and **behind a consent** step (GDPR).
- Track the activation funnel: **signup → add language → first generate → first review**, plus
  D1/D7 retention, reviews/day, and feature usage (Discover, tap-a-word).
- No PII in events; honor opt-out; disclose it in the privacy policy.

## SLOs (set targets, then measure)

- **Availability**: e.g. 99.5% monthly for the API (cold starts count).
- **Latency**: p95 < X ms for non-Gemini routes; Gemini routes measured separately (provider
  latency dominates — track but don't SLO the model itself).
- **Error budget**: define and watch; wire burn-rate alerts once there's traffic.

## Correlation checklist (the test for "done")

- [ ] A single user action produces one trace spanning client → API → DB and/or Gemini.
- [ ] Logs for that request carry the same `trace_id`.
- [ ] A thrown error appears in Sentry with the `trace_id` to jump to the Grafana trace.
- [ ] The cost-guard dashboard shows live Gemini usage vs ceiling.
- [ ] A deliberately triggered alert reaches your real notification channel.
