# Grafana dashboards (as code)

Phase 5.6 dashboards for Lengua, committed as JSON so they are **reproducible per environment**.
They visualize the OpenTelemetry signals the backend emits (Phase 3.8 / 5.2) once those are
exported to Grafana Cloud (Mimir for metrics, Loki for logs, Tempo for traces).

| File | uid | Task | What it shows |
|------|-----|:----:|---------------|
| [`dashboards/service-health.json`](dashboards/service-health.json) | `lengua-service-health` | 5.6.1 | RED: request rate, 5xx error rate, p50/p95/p99 latency per route |
| [`dashboards/cost-guard.json`](dashboards/cost-guard.json) | `lengua-cost-guard` | 5.6.2 | **stay free:** calls/day vs the `GLOBAL_DAILY_BUDGET` ceiling, `llm_budget_remaining`, quota blocks by gate, tokens/day |
| [`dashboards/product.json`](dashboards/product.json) | `lengua-product` | 5.6.3 | reviews/day, cards created, signups, active users (CEFR distribution pending a metric) |
| [`dashboards/infra.json`](dashboards/infra.json) | `lengua-infra` | 5.6.4 | **Phase-6 skeleton** — Cloud Run instances/cold starts, DB latency, Loki error feed (placeholders; not wired until the Cloud Run deploy) |

## How to provision / import

Each dashboard declares a `datasource`-type template variable (the infra skeleton also declares a
`loki_datasource`), so panels are **not** pinned to a specific data-source UID — pick the
environment's Prometheus/Mimir (and Loki) source on import. Two ways to load them:

- **UI:** Grafana → Dashboards → New → Import → upload the JSON (or paste it), then choose the data
  source for the `datasource` variable.
- **Provisioning (recommended for staging/prod, Phase 6):** mount this directory and point a
  [dashboard provider](https://grafana.com/docs/grafana/latest/administration/provisioning/#dashboards)
  at it:

  ```yaml
  # /etc/grafana/provisioning/dashboards/lengua.yaml
  apiVersion: 1
  providers:
    - name: lengua
      type: file
      allowUiUpdates: false
      options:
        path: /var/lib/grafana/dashboards/lengua   # infra/grafana/dashboards/ contents
        foldersFromFilesStructure: false
  ```

## Metric-name policy (read before editing a query)

Dashboards must reference the **real emitted** metric names — the provider-agnostic `llm_*`/`*_total`
names, never the stale `gemini_*` names from the original plan text (reconciliation in
[`planning/outstanding-work.md`](../../planning/outstanding-work.md) §11). The
[`apps/api/tests/obs/test_dashboards.py`](../../apps/api/tests/obs/test_dashboards.py) drift test
fails CI if a panel references a metric the backend does not emit, cross-referencing every PromQL
metric name against the instruments discovered in
[`app/llm_observability.py`](../../apps/api/app/llm_observability.py) +
[`app/product_metrics.py`](../../apps/api/app/product_metrics.py) plus the FastAPI request-duration
histogram.

Emitted instruments (OTel names) and the panels that use them:

| OTel instrument | Type | Labels | Used by |
|-----------------|------|--------|---------|
| `llm_calls_total` | counter | `kind`, `result` | cost-guard |
| `llm_cap_hits_total` | counter | `gate` | cost-guard (this is the plan's `quota_blocks_total{reason}`) |
| `llm_tokens_total` | counter | `kind`, `direction` | cost-guard |
| `llm_budget_remaining` | observable gauge | — | cost-guard |
| `reviews_total` | counter | — | product |
| `cards_created_total` | counter | — | product |
| `signups_total` | counter | — | product |
| `active_users` | observable gauge | — | product |
| `http.server.duration` | histogram (FastAPI instrumentation, unit `ms`) | route + status | service-health |

### One environment-specific knob: the histogram metric name

The `llm_*`/`*_total`/gauge instruments are already valid Prometheus names and are referenced
verbatim. The **FastAPI request-duration histogram** is the exception: its OTel name is
`http.server.duration` (unit `ms`). Under the **default** OTLP→Prometheus translation
(`UnderscoreEscapingWithSuffixes`, which Grafana Cloud applies) it lands as
`http_server_duration_milliseconds` with the usual `_bucket` / `_count` / `_sum` series, and the
route label is `http_target` (the pinned old-HTTP-semconv instrumentation labels the *metric* with
the request path; the *span* carries `http.route`). The service-health panels use that suffixed
form.

If your environment is configured **without** unit suffixes, drop `_milliseconds`
(`http_server_duration_bucket` / `_count`); if it upgrades to the stable HTTP semconv the histogram
becomes `http_server_request_duration_seconds` and the route label becomes `http_route`. The drift
test accepts the suffixed and unsuffixed forms; confirm the exact name in Grafana Explore at deploy
time (owner/Phase-6 — see below).

## CI-verified vs. owner-deferred

- **CI-verified (this PR):** the JSON is valid Grafana dashboard JSON, uids/panel-ids are unique,
  every panel uses a declared datasource variable, and every production-dashboard metric maps to an
  emitted instrument. `apps/api/tests/obs/test_dashboards.py` enforces all of this on every PR.
- **Owner / Phase-6 (deferred, not ticked here):** the live "renders non-empty after a load script"
  confirmation needs a deployed service + live Grafana Cloud creds. The **infra dashboard (5.6.4)**
  is a skeleton that depends entirely on the Cloud Run deploy. Both are logged in
  [`planning/outstanding-work.md`](../../planning/outstanding-work.md) §11.
