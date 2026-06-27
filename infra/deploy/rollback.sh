#!/usr/bin/env bash
# infra/deploy/rollback.sh — one-click Cloud Run rollback (Phase 6 task 6.8.2).
#
# Shifts 100% of a Cloud Run service's traffic back to its previous good revision — no rebuild, no
# redeploy. Cloud Run retains old revisions by default, so the previous revision is always there to
# roll back to. By default the script rolls back to the newest READY revision that is NOT the one
# currently serving traffic; pass an explicit revision name to target a specific one.
#
# Usage (from the repo root, via Git Bash / WSL / any bash):
#   GCP_PROJECT_ID=lengua-prod GCP_REGION=europe-west1 infra/deploy/rollback.sh lengua-api-staging
#   GCP_PROJECT_ID=lengua-prod GCP_REGION=europe-west1 infra/deploy/rollback.sh lengua-api-prod lengua-api-prod-00012-abc
#
# Defaults: project = $GCP_PROJECT_ID, region = $GCP_REGION (export them or prefix the command).
#
# PowerShell note: this is a bash script — run it through Git Bash or WSL. If you prefer pure
# PowerShell, run the three gcloud commands it performs directly (gcloud itself is cross-platform):
#   gcloud run revisions list --service <svc> --region $env:GCP_REGION --project $env:GCP_PROJECT_ID
#   gcloud run services update-traffic <svc> --region ... --project ... --to-revisions <rev>=100
#   then curl/Invoke-WebRequest "<service-url>/health".
#
# See docs/runbook.md "Rollback" for the full operator procedure (incl. rolling forward and the
# bad-migration caveat).
set -euo pipefail

SERVICE="${1:?usage: rollback.sh <service> [target-revision]}"
TARGET_REV="${2:-}"
REGION="${GCP_REGION:?set GCP_REGION (e.g. europe-west1)}"
PROJECT="${GCP_PROJECT_ID:?set GCP_PROJECT_ID (e.g. lengua-prod)}"

echo "Service: $SERVICE   Region: $REGION   Project: $PROJECT"
echo
echo "Current revisions (newest first):"
gcloud run revisions list --service "$SERVICE" --region "$REGION" --project "$PROJECT" \
  --sort-by="~metadata.creationTimestamp" \
  --format='table(metadata.name, status.conditions[0].lastTransitionTime, spec.containers[0].image)'

# The revision currently serving the primary traffic split.
current="$(gcloud run services describe "$SERVICE" --region "$REGION" --project "$PROJECT" \
  --format='value(status.traffic[0].revisionName)')"

if [ -z "$TARGET_REV" ]; then
  # Newest READY revision that is NOT the one currently serving traffic = the previous good one.
  TARGET_REV="$(gcloud run revisions list --service "$SERVICE" --region "$REGION" --project "$PROJECT" \
    --sort-by="~metadata.creationTimestamp" --format='value(metadata.name)' \
    | grep -vx "$current" | head -n1)"
fi

if [ -z "$TARGET_REV" ]; then
  echo "ERROR: no previous revision to roll back to (need >=2 retained revisions)." >&2
  exit 1
fi

echo
echo "Currently serving : ${current:-<unknown>}"
echo "Rolling back to    : $TARGET_REV  (100% traffic)"
gcloud run services update-traffic "$SERVICE" --region "$REGION" --project "$PROJECT" \
  --to-revisions "${TARGET_REV}=100"

url="$(gcloud run services describe "$SERVICE" --region "$REGION" --project "$PROJECT" \
  --format='value(status.url)')"
echo
echo "Verifying ${url}/health ..."
if curl -fsS "${url}/health" >/dev/null; then
  echo "Rollback OK — $SERVICE now serves $TARGET_REV and /health returned 200."
else
  echo "WARNING: /health did not return 200 after rollback — investigate immediately." >&2
  exit 1
fi
