# infra/deploy

Deploy & rollback tooling for the Cloud Run services (`lengua-api-staging` / `lengua-api-prod`).

The CD pipeline itself is committed as GitHub Actions workflows (GitHub only auto-discovers
workflows under `.github/workflows/`):

- [`.github/workflows/deploy-staging.yml`](../../.github/workflows/deploy-staging.yml) — on push
  to `main`: build + push the API image, migrate staging, deploy Cloud Run staging, deploy Vercel
  staging, smoke-check (group 6.6).
- [`.github/workflows/deploy-prod.yml`](../../.github/workflows/deploy-prod.yml) — manual /
  release: gated `production` approval → promote the staging-validated image digest, migrate prod,
  deploy Vercel prod, smoke-check (group 6.7).
- Shared composite actions: [`.github/actions/cloud-run-deploy`](../../.github/actions/cloud-run-deploy)
  (auth + `gcloud run deploy` + URL output) and
  [`.github/actions/cloud-run-smoke`](../../.github/actions/cloud-run-smoke) (`/health` + `/ready`
  + web probes).

**Both deploy workflows are inert until the owner sets the repo variable `DEPLOY_ENABLED=true`**
(`gh variable set DEPLOY_ENABLED -b true`). Every job is gated `if: vars.DEPLOY_ENABLED == 'true'`,
so with the variable unset each push to `main` runs a green no-op. See
[`planning/go-live-activation.md`](../../planning/go-live-activation.md) for the owner activation
runbook and [`planning/outstanding-work.md`](../../planning/outstanding-work.md) for the
live-deferred verifies.

## `rollback.sh` — one-click rollback (task 6.8.2)

Shifts 100% of a service's traffic back to its previous good revision (no rebuild/redeploy). Cloud
Run retains old revisions by default, so the previous one is always available.

```bash
# Roll staging back to the previous revision (auto-selected):
GCP_PROJECT_ID=lengua-prod GCP_REGION=europe-west1 infra/deploy/rollback.sh lengua-api-staging

# Roll prod back to a SPECIFIC revision:
GCP_PROJECT_ID=lengua-prod GCP_REGION=europe-west1 \
  infra/deploy/rollback.sh lengua-api-prod lengua-api-prod-00012-abc
```

It is bash — on Windows run it via Git Bash / WSL, or run the gcloud commands directly in
PowerShell (gcloud is cross-platform). Full operator context (rolling forward, the bad-migration
caveat, the Vercel rollback) is in [`docs/runbook.md`](../../docs/runbook.md) "Rollback".
