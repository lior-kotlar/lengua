# External uptime monitor (as code)

Task **5.8.1**: a free, **external** prober that watches production `/health` every few minutes,
independent of the app's own Grafana/OTel stack — so it still fires when the whole stack (or the
Cloud Run service) is down. This is the last line of "is the site even up?" defense.

[`uptime-monitor.yaml`](uptime-monitor.yaml) is a **vendor-neutral descriptor** of the intended
monitor plus ready-to-use encodings for three free probers:

- **BetterStack (Better Uptime)** — Terraform-style resource (reproducible as code).
- **UptimeRobot** — free tier (5-minute minimum interval).
- **Grafana Synthetic Monitoring** — emits the `probe_success` metric that the Grafana alert
  `lengua-health-uptime-down` ([`../grafana/alerts/alert-rules.yaml`](../grafana/alerts/alert-rules.yaml),
  task 5.7.5) evaluates, unifying the external check with Grafana alerting.

The monitor: `GET ${PROD_BASE_URL}/health`, expect `200` + body `{"status":"ok"}`, every 3 minutes,
alert on failure to the on-call contact (the same channel as
[`../grafana/alerts/contact-points.yaml`](../grafana/alerts/contact-points.yaml)).

## CI-verified vs. owner / Phase-6 deferred

- **CI-verified (this PR):** the descriptor parses and is structurally valid — it targets `/health`,
  runs on a few-minute interval, alerts on failure, and names a contact
  ([`apps/api/tests/obs/test_alerts.py`](../../apps/api/tests/obs/test_alerts.py)).
- **Owner / Phase-6 (deferred, NOT ticked):** the live verify — the monitor dashboard shows prod
  `/health` green at the interval and flips to **DOWN** with a notification when the endpoint fails —
  needs the **real prod URL (the Cloud Run deploy, Phase 6) and a free-prober account (owner)**. The
  `${PROD_BASE_URL}` placeholder is filled at deploy. Logged in
  [`planning/outstanding-work.md`](../../planning/outstanding-work.md) §11 and summarized in
  [`docs/runbook.md`](../../docs/runbook.md).
