# Grafana alerting (as code)

Phase 5.7 alerting for Lengua, committed as **Grafana provisioned-alerting** YAML so the alert
conditions, routing, and contact targets are reproducible per environment. These files pair with the
dashboards in [`../dashboards/`](../dashboards) and the external uptime monitor in
[`../../uptime/`](../../uptime).

| File | Task | What it defines |
|------|:----:|-----------------|
| [`contact-points.yaml`](contact-points.yaml) | 5.7.1 | The `lengua-oncall` contact point (Slack primary; email / Discord alternatives), all secrets as env-expanded placeholders |
| [`notification-policies.yaml`](notification-policies.yaml) | 5.7.1 | The notification policy tree routing every alert to `lengua-oncall`, grouped/paced by `severity` |
| [`alert-rules.yaml`](alert-rules.yaml) | 5.7.2 – 5.7.5 | Four alert rules: API 5xx spike, sustained p95 latency, LLM budget ≥ 80% consumed, prod `/health` uptime down |

## The rules

| uid | Task | Fires when | `for` | Severity | Metric |
|-----|:----:|------------|:-----:|----------|--------|
| `lengua-api-5xx-spike` | 5.7.2 | 5xx ratio > 5% | 5m | critical | `http_server_duration_milliseconds_count{http_status_code=~"5.."}` |
| `lengua-api-p95-latency` | 5.7.3 | overall p95 > 1500 ms | 10m | warning | `http_server_duration_milliseconds_bucket` |
| `lengua-llm-budget-80pct` | 5.7.4 | `llm_budget_remaining` < 20% of ceiling | 5m | warning | `llm_budget_remaining` |
| `lengua-health-uptime-down` | 5.7.5 | `probe_success` < 1 (prod `/health` DOWN) | 1m | critical | `probe_success` (external probe — see [`../../uptime/`](../../uptime)) |

The LLM-budget threshold (200) is **20% of the default `GLOBAL_DAILY_BUDGET` (1000)** — the early
warning before the Phase-3 global kill-switch trips at 0. If you change `GLOBAL_DAILY_BUDGET` at
deploy, update the threshold to `0.2 × ceiling`; the lint test
([`apps/api/tests/obs/test_alerts.py`](../../../apps/api/tests/obs/test_alerts.py)) enforces that
relationship against the configured default so the two can't silently drift.

## Metric-name policy

The PromQL references the **real emitted** metric names — the provider-agnostic `llm_*` names and the
FastAPI request-duration histogram — exactly as the dashboards do (see
[`../README.md`](../README.md) for the full policy and the one env-specific histogram-suffix knob).
`probe_success` is the **one external** metric: it is produced by the uptime probe (Grafana Synthetic
Monitoring / Blackbox exporter, task 5.8.1), not by the app, so the lint test allow-lists it
explicitly rather than cross-referencing it against an emitted instrument.

## How to provision

[Provision alerting resources](https://grafana.com/docs/grafana/latest/alerting/set-up/provision-alerting-resources/)
by mounting these files into Grafana's alerting provisioning directory (Grafana Cloud: import via
the alerting provisioning API / Terraform). Grafana substitutes `${VAR}` placeholders from its
environment, so set:

| Env var | Used by | Value |
|---------|---------|-------|
| `PROM_DATASOURCE_UID` | every rule's query stage | the Prometheus/Mimir data-source UID in the target Grafana |
| `SLACK_WEBHOOK_URL` | the Slack receiver | the real Slack incoming-webhook URL |
| `ALERT_EMAIL_ADDRESSES` / `DISCORD_WEBHOOK_URL` | the optional receivers | only if you enable those channels |

## CI-verified vs. owner / Phase-6 deferred

- **CI-verified (this PR):** every file parses, each rule's `condition` refId exists in its `data`,
  uids are unique, the budget threshold tracks `GLOBAL_DAILY_BUDGET`, and every PromQL metric maps to
  an emitted instrument (or the allow-listed external `probe_success`).
  [`apps/api/tests/obs/test_alerts.py`](../../../apps/api/tests/obs/test_alerts.py) enforces all of
  this on every PR.
- **Owner / Phase-6 (deferred, NOT ticked):** the live verifies — a contact-point "Test" delivers to
  the real channel (5.7.1); a forced 5xx / latency / budget / uptime condition on **staging traffic**
  fires the alert to that channel (5.7.2 – 5.7.5) — need live Grafana Cloud creds + a deployed
  Cloud Run service (Phase 6). They are logged in
  [`planning/outstanding-work.md`](../../../planning/outstanding-work.md) §11 and summarized in
  [`docs/runbook.md`](../../../docs/runbook.md).
