# Runbook

> **Placeholder.** This is a Phase 0 stub. The operational runbook is filled in
> as the deploy pipeline and observability land (Phases 5–6) and is finalized for
> launch (Phase 9). The sections below are intentionally empty for now.

## Health checks

How to tell — at a glance and in depth — whether Lengua is healthy, and where to look when it is
not. The **live** wiring (Grafana Cloud dashboards/alerts, the deployed service, a real notification
channel) is stood up in Phase 6; the signals and as-code config below are in place now.

### The `/health` endpoint

The API exposes a liveness probe:

```
GET /health  →  200 {"status":"ok"}
```

It is unauthenticated, does no DB/LLM work, and is consumed by **Cloud Run** (the startup +
liveness probes — so a transient DB blip never *kills* a serving instance), the **CI smoke check**,
and the **external uptime monitor** (below). Quick manual check:

```bash
curl -fsS https://<prod-host>/health    # expect: {"status":"ok"}
```

- **Green:** `200 {"status":"ok"}`.
- **Red:** non-200, a timeout, or no response → the instance is down or unreachable; check Cloud Run
  instance health and recent deploys, then escalate per the On-call section.

### The `/ready` endpoint

The API also exposes a **readiness** probe — distinct from liveness:

```
GET /ready  →  200 {"status":"ready"}   |   503 {"status":"not_ready"}
```

It is unauthenticated like `/health`, but additionally verifies **database connectivity**: a
lightweight `SELECT 1` on a plain (RLS-free) engine connection — no JWT, never the `authenticated`
role — bounded by a short timeout. It answers `200 {"status":"ready"}` when the DB responds and
`503 {"status":"not_ready"}` (never `500`) when it cannot. **Cloud Run's readiness probe points at
`/ready`** so an instance that has lost its database is pulled from rotation without being killed,
while the startup + liveness probes stay on the DB-free `/health` above. (The probe *wiring* in the
Cloud Run service config lands with the CD pipeline, group 6.6.)

```bash
curl -i https://<prod-host>/ready    # expect: 200 {"status":"ready"} (or 503 when the DB is down)
```

### Observability signals (Grafana Cloud)

Every signal is tagged `service.name=lengua-api` + `deployment.environment` (`local|staging|prod`),
so filter by those in Grafana. Export is OTLP and only active when `OTEL_EXPORTER_OTLP_ENDPOINT` is
set (Phase 6 staging/prod); locally/CI it is a no-op.

- **Traces → Grafana Tempo.** One user action is a single trace spanning client → API → DB / LLM
  (the web client injects a W3C `traceparent`; the API continues it). Search Tempo's Explore by
  `service.name=lengua-api`. A custom `llm.call` span carries provider/model/latency/tokens; a
  `quota.check` span carries the cost-guard decision.
- **Logs → Grafana Loki.** Structured JSON access lines (one per request: method/path/status/
  latency_ms) plus app logs, each correlated by `trace_id` / `span_id` (and `user_id` for
  in-request logs). Filter by `service_name="lengua-api"`; from a Tempo trace, jump to its logs via
  the Tempo→Loki "trace to logs" link.
- **Metrics + dashboards → Grafana (Mimir).** Dashboards are committed as code under
  [`infra/grafana/dashboards/`](../infra/grafana/dashboards) (see
  [`infra/grafana/README.md`](../infra/grafana/README.md)):
  - **Service health (RED)** (`lengua-service-health`) — per-route request rate, 5xx error rate, and
    p50/p95/p99 latency. *Green:* low/flat 5xx ratio, p95 within target. *Red:* a climbing 5xx ratio
    or a latency spike on a route.
  - **LLM cost guard** (`lengua-cost-guard`) — the "stay free" board: `llm_budget_remaining` vs the
    `GLOBAL_DAILY_BUDGET` ceiling, calls/day, quota blocks by gate, tokens/day. *Green:* budget
    remaining comfortably above 0, few/no blocks. *Red:* `llm_budget_remaining` approaching 0 (the
    kill-switch refuses every LLM call at 0 with HTTP 429 `daily_limit_reached`) or a surge of
    `llm_cap_hits_total` blocks.
  - **Product** (`lengua-product`) — reviews/day, cards created, signups, active users.
  - **Infra** (`lengua-infra`) — Phase-6 skeleton (Cloud Run instances/cold starts, DB latency, Loki
    error feed); populated once the Cloud Run deploy lands.

### Alerts

Alerts are committed as code (Grafana provisioned alerting) under
[`infra/grafana/alerts/`](../infra/grafana/alerts) (see its
[README](../infra/grafana/alerts/README.md)). All route to the `lengua-oncall` contact point
(Slack primary; email/Discord alternatives — the real webhook/address is an owner-set placeholder).

| Alert | Fires when | Severity |
|-------|------------|----------|
| API 5xx error-rate spike | 5xx ratio > 5% for 5m | critical |
| API p95 latency high | overall p95 > 1.5s for 10m | warning |
| LLM daily budget 80% consumed | `llm_budget_remaining` < 20% of ceiling | warning (early warning before the kill-switch) |
| prod `/health` uptime down | the uptime probe reports DOWN | critical |

When an alert fires, open the linked dashboard, confirm the condition, and follow the On-call
first-response checklist.

### External uptime monitor

A free, **external** prober (independent of the app's own stack) watches prod `/health` every few
minutes and alerts on failure — config as code in [`infra/uptime/`](../infra/uptime). It is the
last-line "is the site even up?" signal and the source of the prod-`/health` uptime alert above.

### What "healthy" looks like

- **API:** `/health` 200; 5xx ratio near 0; p95 within target; `llm_budget_remaining` > 0.
- **Web:** loads and authenticates; no spike in Sentry JS errors (web DSN).
- **Database:** queries succeed (no DB-error logs in Loki); DB-latency panel within normal range.

> **Live wiring is Phase 6 + owner.** Finding the trace in Tempo, the log in Loki, a dashboard
> rendering non-empty, and an alert reaching a real channel each need live Grafana Cloud creds and a
> deployed Cloud Run service — tracked in [`planning/outstanding-work.md`](../planning/outstanding-work.md) §11.

## Deploy / rollback

_Filled in Phase 6 (CD pipeline): how to deploy to staging and production, how to promote a build,
and the exact steps to roll back a bad release._

> **Schema invariant — never migrate prod with Alembic-only.** `DELETE /account` relies on the
> `auth.users → profiles` `ON DELETE CASCADE` present in the canonical Supabase schema
> (`supabase/migrations/...`), which the bare Alembic-0001 schema intentionally omits (it has no
> `auth` schema to reference); prod is Supabase so the cascade holds, but prod must **never** be
> migrated via Alembic-only or a deletion would orphan the profile and all domain data.

> **Cost-guard invariant — never `alembic downgrade` past `0004` in prod.** Migration `0004`
> (`llm_killswitch`) is what makes the global daily kill-switch (`llm_budget`) server-only: it
> `REVOKE`s the counter tables from `authenticated`/`anon`, puts `llm_budget` under deny-by-default
> RLS, and exposes writes only through `SECURITY DEFINER` functions granted to `service_role`. Its
> `downgrade` re-grants `authenticated`/`anon` access to `llm_budget` and drops those functions —
> **re-exposing the kill-switch to any logged-in user via PostgREST**. Downgrading past `0004` in
> production would let a user trip or hide the cost guard for everyone; treat `0004` as a one-way
> migration in prod.

## On-call

_Filled in for launch (Phase 9): on-call rotation, escalation path, alert routing, and the
first-response checklist for an incident. Alert routing is wired as code now — see "Health checks →
Alerts" above and [`infra/grafana/alerts/`](../infra/grafana/alerts)._

## Historical data import (legacy SQLite → Postgres)

One-off migration of the operator's pre-productionization learning history from the legacy
single-user SQLite database (`apps/api/data/lengua.db`) into the new multi-tenant Postgres
schema, under the operator's real account. Run by `apps/api/scripts/import_sqlite.py` (task 2.7).

**Prerequisites**

- The target account already exists in Supabase Auth (the operator has signed up), so its
  `profiles` row exists. Get the account UUID from the Supabase dashboard (Authentication →
  Users) or `select id from auth.users where email = '<operator email>'`.
- A **privileged** `DATABASE_URL` (the `postgres` superuser DSN, e.g. from the Supabase project's
  connection settings). RLS makes the request-path role (`authenticated`) unable to write another
  user's rows, so the import **must** use the privileged connection — never the app's request path.
- A copy of the legacy `data/lengua.db` reachable from where you run the script.

**Procedure** (run from `apps/api`):

```bash
# 1. Dry run first — reports the planned inserts per table, writes NOTHING.
uv run python scripts/import_sqlite.py \
    --user-id <OPERATOR_UUID> \
    --sqlite-path data/lengua.db \
    --database-url "$DATABASE_URL" \
    --dry-run

# 2. Real import once the dry-run counts look right.
uv run python scripts/import_sqlite.py \
    --user-id <OPERATOR_UUID> \
    --sqlite-path data/lengua.db \
    --database-url "$DATABASE_URL"
```

`--sqlite-path` defaults to `data/lengua.db` and `--database-url` to `$DATABASE_URL`, so both can
be omitted when running with those defaults.

**What it does:** maps the old integer/global schema to the new schema, stamping every
`languages` / `cards` / `reviews` / `proficiency` row (and the legacy `settings` → `user_settings`)
with the target `user_id`, preserving `fsrs_state`, `due`, `saved`, and the proficiency scores.
Old integer ids are remapped to the new identity ids (parent → child), so the import never
collides with rows the account already created in the app.

**Idempotency / re-running:** the import is guarded by a natural key per table (languages on
`(user_id, name)`, cards on `(user_id, language_id, front, back, direction)`, reviews on
`(user_id, card_id, rating, reviewed_at)`, and the composite-PK `proficiency` / `user_settings`),
so re-running inserts nothing new — the row counts stay the same. The whole import runs in a single
transaction (all-or-nothing); `--dry-run` rolls that transaction back.

**Verify after import:** the per-table `inserted` counts in the report match the source row counts,
and a spot check of the operator's deck (`GET /review/due` after logging in, or a direct
`select count(*) from cards where user_id = '<OPERATOR_UUID>'`) shows the expected cards.
