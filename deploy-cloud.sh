#!/usr/bin/env bash
# Cloud Run deploy — stretch goal, gated at 17:00 on build day (docs/PLAN.md).
# Never run this to fix a broken LOCAL path: LOCAL must remain runnable at all
# times, and this script never touches it. Switching is configuration only —
# see docs/CLAUDE.md § Two deployment targets.
set -euo pipefail

PROJECT_ID="${GCP_PROJECT_ID:-sfws-aicc-workspace-1}"
REGION="${GCP_REGION:-asia-southeast1}"
SERVICE_NAME="${SERVICE_NAME:-huluhilir-api}"

echo "Deploying $SERVICE_NAME to Cloud Run in $REGION (project: $PROJECT_ID)"

gcloud run deploy "$SERVICE_NAME" \
  --source ./backend \
  --project "$PROJECT_ID" \
  --region "$REGION" \
  --allow-unauthenticated \
  --min-instances 1 \
  --set-env-vars "LITELLM_MODEL=vertex_ai/gemini-2.0-flash" \
  --set-env-vars "VERTEX_PROJECT=$PROJECT_ID" \
  --set-env-vars "VERTEX_LOCATION=$REGION" \
  --set-env-vars "DATABASE_URL=sqlite+aiosqlite:////tmp/huluhilir.db"

echo
echo "Deployed. Fetching public URL:"
gcloud run services describe "$SERVICE_NAME" --project "$PROJECT_ID" --region "$REGION" --format="value(status.url)"

echo
echo "Verify with: curl <URL>/health"
echo "Remember: build the cloud-target APK with --dart-define=API_BASE_URL=<URL> (docs/CLAUDE.md § Commands)."
