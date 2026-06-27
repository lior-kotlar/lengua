# Runbook

> The operational runbook. **Health checks** (Phase 5) and **Deploy / Rollback / Run a migration /
> Rotate a secret / Budget-exhausted alert / Restore from backup** (Phase 6) are written with
> concrete commands; **On-call** and the **Store-release checklist** are finalized at launch
> (Phase 9). The procedures are buildable-as-code now; their **live execution** against deployed
> cloud resources is owner-run and tracked in
> [`planning/outstanding-work.md`](../planning/outstanding-work.md) §§11–12.

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

## Deploy

How a build reaches staging and prod. The pipeline is committed as code (CD workflow, groups 6.6 +
6.7) and is **gated off until the owner sets the repo variable `DEPLOY_ENABLED=true`**
(`gh variable set DEPLOY_ENABLED -b true`); the manual `gcloud` path below is the same set of steps
and is what the workflow automates. Concrete owner values are `<placeholders>`; the real ones live
in Secret Manager / GitHub Actions secrets (never git). Throughout: GCP project `lengua-prod`,
EU region `$GCP_REGION`, Artifact Registry repo `${GCP_REGION}-docker.pkg.dev/lengua-prod/lengua`,
Cloud Run services `lengua-api-staging` / `lengua-api-prod`.

### Staging (automatic on merge to `main`)

Merging to `main` is the staging-deploy trigger. The CD run, in order (6.6.1–6.6.5):

1. **Build + push** the API image tagged with the merge commit SHA:
   ```bash
   SHA="$(git rev-parse HEAD)"
   gcloud builds submit apps/api \
     --tag "${GCP_REGION}-docker.pkg.dev/lengua-prod/lengua/api:${SHA}" --project lengua-prod
   ```
2. **Migrate staging** as a discrete, logged job — see "Run a migration" (never in the request path).
3. **Deploy** the freshly pushed image as a new Cloud Run revision:
   ```bash
   gcloud run deploy lengua-api-staging \
     --image "${GCP_REGION}-docker.pkg.dev/lengua-prod/lengua/api:${SHA}" \
     --region "$GCP_REGION" --project lengua-prod
   ```
4. **Deploy web** to Vercel staging (`vercel deploy` / the Vercel GitHub integration).
5. **Smoke** the deploy: `GET /health` 200, `GET /ready` 200, web `200`. A failed probe reds the run.

Run config (secrets mounted, not inlined) is set once on the service — see "Rotate a secret" and
task 6.4.1 for the secret list (`LLM_PROVIDER`, `GROQ_API_KEY`, `DATABASE_URL`,
`SUPABASE_JWT_SECRET`, `OTEL_*`, `SENTRY_DSN_API`, quota ceilings).

### Production (gated promotion)

Prod is a **single manual approval** (the GitHub `production` environment reviewer, 6.7.1) that
**promotes the exact image digest already validated on staging — no rebuild** (6.7.2):

```bash
# The digest currently serving staging:
DIGEST="$(gcloud run services describe lengua-api-staging --region "$GCP_REGION" \
  --project lengua-prod --format='value(spec.template.spec.containers[0].image)')"

# After the approval gate: migrate prod (gated job, see below), then promote the SAME digest:
gcloud run deploy lengua-api-prod --image "$DIGEST" --region "$GCP_REGION" --project lengua-prod
```

Then the gated prod migration (6.7.3) and Vercel **production** deploy (6.7.4) run, ending with prod
smoke probes (6.7.5). The previous revision is retained for one-click rollback (below).

## Rollback

Cloud Run keeps the previous revision, so a bad release is reverted by **shifting 100% traffic back
to the last good revision** — no rebuild, no redeploy. Group 6.8.2 adds a one-command wrapper
(`infra/deploy/rollback.sh <service>`); until it lands, run these directly (swap `-staging` for
`-prod` to roll back prod):

```bash
# 1. List revisions newest-first and see which serves traffic + which image each runs:
gcloud run revisions list --service lengua-api-staging --region "$GCP_REGION" --project lengua-prod \
  --format='table(metadata.name, status.conditions[0].lastTransitionTime, spec.containers[0].image)'

# 2. Shift 100% traffic to the previous good revision (use its exact name from step 1):
gcloud run services update-traffic lengua-api-staging --region "$GCP_REGION" --project lengua-prod \
  --to-revisions=<previous-good-revision>=100

# 3. Verify the rollback serves healthy from the old code:
URL="$(gcloud run services describe lengua-api-staging --region "$GCP_REGION" \
  --project lengua-prod --format='value(status.url)')"
curl -fsS "$URL/health"   # → {"status":"ok"}
```

To roll forward again once a fix is deployed: `--to-latest` instead of `--to-revisions=...`. If a bad
migration is implicated, roll the service back first (restores availability), then assess the schema
separately — schema is forward-only in prod (see the migration invariants below). **Web (Vercel):**
`vercel rollback <previous-deployment-url>` (or promote the previous deployment in the dashboard).

## Run a migration

Alembic owns the schema and is applied as a **discrete, logged job** (CD groups 6.6.3 staging /
6.7.3 gated prod) — separate from the image deploy, **never in the request path**. Run from
`apps/api`.

**Environment selection:** the Alembic env (`migrations/env.py`) resolves the target DB from
`-x db_url=<dsn>` (preferred for a one-off op) **or** `$DATABASE_URL` — there is **no `-x env=`
switch**. Point it at the env's connection string (the `SUPABASE_{STAGING,PROD}_DATABASE_URL`
secrets):

```bash
# Inspect first — current applied revision vs the latest defined head:
uv run alembic -x db_url="$SUPABASE_STAGING_DATABASE_URL" current
uv run alembic heads          # the target; `current` must equal this after the upgrade

# Apply to staging:
uv run alembic -x db_url="$SUPABASE_STAGING_DATABASE_URL" upgrade head

# Apply to prod (gated — only from the approval-protected prod-migrate job, or manually with care):
uv run alembic -x db_url="$SUPABASE_PROD_DATABASE_URL" upgrade head
```

After a hosted-Supabase upgrade, `\dt` lists the 8 app tables (+ `llm_usage` / `llm_budget`) and the
trigger / RLS / kill-switch from revisions `0002`–`0004` are present (they apply on Supabase because
it has the `authenticated` role + `auth.uid()`). See
[`infra/supabase/README.md`](../infra/supabase/README.md) for how the Alembic schema and the
canonical Supabase-CLI SQL relate.

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

## Rotate a secret

Secrets live per platform — **Secret Manager** (Cloud Run runtime), **GitHub Actions** (deploy
credentials), **Supabase / Vercel** (their own) — never in git (task 6.4). Rotation is always
**add-the-new → cut-over → verify → revoke-the-old**, so a bad new value never causes an outage with
no way back. Cloud Run pins a secret version per revision, so a new version is only picked up by a
**new revision** (a redeploy). Below, `lengua-api-staging` / `$GCP_REGION` / project `lengua-prod`.

### Groq API key (`GROQ_API_KEY`)

```bash
# 1. Mint a NEW key in the Groq console (https://console.groq.com/keys) — keep the old one ENABLED.
# 2. Add it as a new Secret Manager version (pipe the value; no shell-history echo):
printf '%s' '<new-groq-key>' | gcloud secrets versions add GROQ_API_KEY --data-file=- --project lengua-prod
# 3. Roll a new Cloud Run revision so the service re-resolves GROQ_API_KEY:latest:
gcloud run services update lengua-api-staging --region "$GCP_REGION" --project lengua-prod \
  --update-secrets=GROQ_API_KEY=GROQ_API_KEY:latest
# 4. Verify a generate call still succeeds against the service URL (Groq answers with sentences).
# 5. Revoke the OLD key in the Groq console; optionally disable the old Secret Manager version:
#    gcloud secrets versions disable <N> --secret=GROQ_API_KEY --project lengua-prod
```

Repeat for `lengua-api-prod`. The same shape rotates any Secret-Manager-mounted value
(`SENTRY_DSN_API`, `OTEL_EXPORTER_OTLP_HEADERS`, the quota ceilings, etc.).

### Supabase JWT secret (`SUPABASE_JWT_SECRET`)

Higher-impact: the backend verifies **every** access token against this, so the new value must reach
Cloud Run **in lockstep** with rotating it in Supabase, or every request 401s and all existing
sessions are invalidated (users must re-login). Do it in a low-traffic window.

```bash
# 1. Rotate the JWT secret in the Supabase dashboard (Project Settings → API → JWT Settings).
# 2. IMMEDIATELY update the Secret Manager version with the new value:
printf '%s' '<new-jwt-secret>' | gcloud secrets versions add SUPABASE_JWT_SECRET --data-file=- --project lengua-prod
# 3. Roll a new revision to pick it up:
gcloud run services update lengua-api-staging --region "$GCP_REGION" --project lengua-prod \
  --update-secrets=SUPABASE_JWT_SECRET=SUPABASE_JWT_SECRET:latest
# 4. Verify: a fresh login issues a token the API accepts (an authenticated request returns 200).
```

**Zero-downtime alternative:** prefer Supabase **asymmetric JWT signing keys** (RS256/ES256) over the
shared HS256 secret. The backend can verify via JWKS (`SUPABASE_JWKS_URL`, see `.env.example`), and
Supabase rotates signing keys without invalidating live sessions — no shared-secret cut-over.

### Deploy credential (GCP deployer SA key, `GCP_SA_JSON`)

The CD pipeline authenticates to GCP with the deployer service-account key in the `GCP_SA_JSON`
GitHub Actions secret. Rotate keys periodically:

```bash
# 1. Create a NEW key for the deployer SA:
gcloud iam service-accounts keys create new-key.json \
  --iam-account=<deployer-sa>@lengua-prod.iam.gserviceaccount.com --project lengua-prod
# 2. Replace the GitHub Actions secret (masked; never printed):
gh secret set GCP_SA_JSON < new-key.json
# 3. Re-run a deploy workflow to confirm auth still works (the auth step exits 0).
# 4. Delete the OLD key by id and shred the local file:
gcloud iam service-accounts keys list --iam-account=<deployer-sa>@lengua-prod.iam.gserviceaccount.com --project lengua-prod
gcloud iam service-accounts keys delete <old-key-id> \
  --iam-account=<deployer-sa>@lengua-prod.iam.gserviceaccount.com --project lengua-prod
rm -f new-key.json
```

**Preferred long-term:** migrate CD auth to **Workload Identity Federation** (keyless, no SA JSON to
store or rotate); then there is no `GCP_SA_JSON` to leak. The Vercel token (`VERCEL_TOKEN`) and
Supabase access token (`SUPABASE_ACCESS_TOKEN`) rotate the same way — regenerate in the provider
dashboard, `gh secret set <NAME>`, re-run a deploy to confirm, revoke the old.

> **Live rotation is owner + a deployed service.** The end-to-end verify (rotate the **staging**
> Groq key, redeploy, confirm the service serves on the new key and the old one no longer works)
> needs the live Cloud Run service + Secret Manager and is owner-run — tracked in
> [`planning/outstanding-work.md`](../planning/outstanding-work.md) §12.

## Respond to a budget-exhausted alert

The LLM cost guard is the "I will never get a bill" backstop. Two signals fire here: the **early
warning** Grafana alert `lengua-llm-budget-80pct` (when `llm_budget_remaining` < 20% of
`GLOBAL_DAILY_BUDGET`), and — if consumption reaches 100% — the **kill-switch** itself, after which
every user gets `HTTP 429 {"code":"daily_limit_reached"}` until UTC midnight.

**1. Confirm the condition.** Open the **LLM cost guard** dashboard (`lengua-cost-guard`):
`llm_budget_remaining` approaching/at 0, and a rise in `llm_cap_hits_total{gate="global_budget"}`.
Cross-check the counter directly (privileged DB URL — `llm_budget` is service-role-only):

```bash
psql "$SUPABASE_PROD_DATABASE_URL" -c \
  "select day, count from llm_budget where day = (now() at time zone 'utc')::date"
# count >= GLOBAL_DAILY_BUDGET means the kill-switch is tripped for the day.
```

**2. Triage legitimate growth vs. abuse.** Look for one hot user in `llm_usage`
(`select user_id, kind, count from llm_usage where day = current_date order by count desc limit 10`)
and at `llm_cap_hits_total{gate}` (are per-user caps / rate limits also firing?). Genuine abuse is
contained by the per-user caps, the rate limiter, and the day-0 signup guard — the global budget is
the last line.

**3. Raise the ceiling SAFELY (only if it is real demand).** `GLOBAL_DAILY_BUDGET` is env-driven
(default 1000). Before raising it, confirm the **new ceiling × max retry attempts (3)** still stays
under the active provider's free requests-per-day (Groq `llama-3.1-8b-instant`) — one counted call
can fan out to 3 real HTTP requests on 429/5xx. Then update the secret/env and roll a new revision:

```bash
printf '%s' '<new-budget>' | gcloud secrets versions add GLOBAL_DAILY_BUDGET --data-file=- --project lengua-prod
gcloud run services update lengua-api-prod --region "$GCP_REGION" --project lengua-prod \
  --update-secrets=GLOBAL_DAILY_BUDGET=GLOBAL_DAILY_BUDGET:latest
```

**Do not** hand-edit the `llm_budget` row to "unblock" unless you understand it re-arms only at the
UTC rollover and that lowering today's count re-opens spend up to the ceiling. If you are near the
provider's hard free limit, the safe action is to **wait for the automatic midnight-UTC reset**
rather than raise the ceiling. Never set `GLOBAL_DAILY_BUDGET` at or above provider RPD ÷ 3.

## Restore from backup

Postgres lives in Supabase, which takes **automated daily backups** (free tier) and supports
**point-in-time recovery (PITR)** on paid tiers. Two recovery paths:

**PITR (paid tier).** Supabase dashboard → Database → Backups → restore to a timestamp. This is
destructive to the project, so for anything but a true disaster **restore into a scratch project**
first and validate, then cut over.

**`pg_dump` → scratch DB drill (works on every tier).** This is also the rehearsal for task 6.8.4:

```bash
# 1. Dump prod (custom format, no owner/ACL so it restores into any role):
pg_dump "$SUPABASE_PROD_DATABASE_URL" --no-owner --no-acl -Fc -f "prod-$(date +%F).dump"

# 2. Restore into a throwaway scratch database (a fresh Supabase project or a local CLI stack):
pg_restore --no-owner --no-acl --clean --if-exists -d "$SCRATCH_DATABASE_URL" "prod-$(date +%F).dump"

# 3. Verify the row counts match expectations:
psql "$SCRATCH_DATABASE_URL" -c "select count(*) from cards"
psql "$SCRATCH_DATABASE_URL" -c "select count(*) from reviews"
```

> **The actual restore drill is owner-run (task 6.8.4).** Running a real `pg_dump` of prod and
> restoring it into a scratch DB needs the live prod connection string + a scratch target — tracked
> in [`planning/outstanding-work.md`](../planning/outstanding-work.md) §12. The procedure above is
> the script to follow when it is exercised.

## Store-release checklist

Mobile (iOS/Android via Capacitor) and the store submission are **Phases 7–9** and are not yet
built. When they are, the release checklist (signing, store metadata, data-safety forms, screenshots,
staged rollout) lives with those phases. Pointers:

- [`planning/tasks/phase-7-mobile.md`](../planning/tasks/phase-7-mobile.md) — native projects,
  signing, OAuth-in-webview, store builds, OTA.
- [`planning/tasks/phase-8-compliance-store.md`](../planning/tasks/phase-8-compliance-store.md) —
  privacy/support URLs, GDPR rights, Apple/Play data-safety, listings, closed tests.
- [`planning/tasks/phase-9-launch.md`](../planning/tasks/phase-9-launch.md) — prod smoke on every
  platform, store submit/promote, domain cutover, the 48-hour launch watch.
- [`planning/go-live-activation.md`](../planning/go-live-activation.md) — the owner-run activation
  track that turns this as-code pipeline into a live, watchable app (staging → gated prod).

## On-call

_Filled in for launch (Phase 9): on-call rotation, escalation path, alert routing, and the
first-response checklist for an incident. Alert routing is wired as code now — see "Health checks →
Alerts" above and [`infra/grafana/alerts/`](../infra/grafana/alerts); deploy/rollback/secret/budget
first-response steps are the sections above._

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
