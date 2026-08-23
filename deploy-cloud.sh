#!/usr/bin/env bash
# Cloud Run deploy — stretch goal, gated at 17:00 on build day (docs/PLAN.md).
# Never run this to fix a broken LOCAL path: LOCAL must remain runnable at all
# times, and this script never touches it. Switching is configuration only —
# see docs/CLAUDE.md § Two deployment targets.
set -euo pipefail

PROJECT_ID="${GCP_PROJECT_ID:-sfws-aicc-workspace-1}"
REGION="${GCP_REGION:-asia-southeast1}"   # Cloud Run's own region -- Sarawak latency
SERVICE_NAME="${SERVICE_NAME:-huluhilir-api}"
# Vertex AI model location is deliberately DIFFERENT from Cloud Run's region:
# gemini-2.0-flash/1.5-flash are not published in asia-southeast1 (confirmed
# 404 on-device, both in asia-southeast1 AND us-central1 for the *-2.0-*/
# *-1.5-* names specifically); gemini-2.5-flash is the model actually
# resolvable for this project, confirmed via a direct GET against
# publishers/google/models/<id>. Re-check that endpoint before assuming any
# other Gemini model name works here -- see docs/BUILD_LOG.md "Cloud deploy".
VERTEX_LOCATION="${GCP_VERTEX_LOCATION:-us-central1}"
GEMINI_MODEL="${GEMINI_MODEL:-gemini-2.5-flash}"

# Cloud SQL Postgres, NOT a SQLite file. Cloud Run's filesystem is ephemeral:
# a SQLite DB there is wiped on every new revision, which was confirmed the
# hard way -- a farm created through the live API vanished as soon as an
# env-var update rolled a new revision. The connection string lives in
# Secret Manager (it contains the DB password) and is injected as
# DATABASE_URL, so nothing in application code knows which engine it is.
SQL_INSTANCE="${SQL_INSTANCE:-huluhilir-db}"
SQL_CONNECTION="$PROJECT_ID:$REGION:$SQL_INSTANCE"
DB_URL_SECRET="${DB_URL_SECRET:-huluhilir-db-url}"

# Uploaded photos and voice labels live in a GCS bucket mounted as a volume,
# NOT on the container filesystem. Cloud Run's disk is ephemeral, so once the
# database moved to Cloud SQL the two fell out of step: observation rows
# survived a redeploy while the images they referenced did not, leaving
# permanently broken photo links -- which is exactly how the block profile
# ended up with no background image. Mounting a bucket makes media as durable
# as the rows pointing at it, and needs no application code: MEDIA_ROOT just
# points at the mount.
# The mount path below is written with a DOUBLE slash on purpose. Git Bash on
# Windows rewrites anything path-shaped, so a single-slash /media reached
# gcloud as "C:/Program Files/Git/media" and was rejected as not a valid unix
# path -- an error naming a value nobody typed. `//media` is left alone by
# msys and collapses to /media at both ends (verified). MSYS_NO_PATHCONV=1 is
# NOT the fix: it breaks gcloud's own launcher, which relies on that same
# conversion to find gcloud.py.
MEDIA_BUCKET="${MEDIA_BUCKET:-huluhilir-media}"

echo "Deploying $SERVICE_NAME to Cloud Run in $REGION (project: $PROJECT_ID)"

# --source . (repo root, not ./backend): the root Dockerfile bakes the
# classifier model in, which a ./backend-scoped build context cannot reach
# (that path only worked locally via docker-compose.yml's volume mount --
# Cloud Run has no equivalent). See docs/BUILD_LOG.md "Cloud deploy".
gcloud run deploy "$SERVICE_NAME" \
  --source . \
  --project "$PROJECT_ID" \
  --region "$REGION" \
  --allow-unauthenticated \
  --min-instances 1 \
  --memory 1Gi \
  --set-env-vars "LITELLM_MODEL=vertex_ai/$GEMINI_MODEL" \
  --set-env-vars "VERTEXAI_PROJECT=$PROJECT_ID" \
  --set-env-vars "VERTEXAI_LOCATION=$VERTEX_LOCATION" \
  --set-env-vars "MEDIA_ROOT=//media" \
  --add-volume "name=media,type=cloud-storage,bucket=$MEDIA_BUCKET" \
  --add-volume-mount "volume=media,mount-path=//media" \
  --add-cloudsql-instances "$SQL_CONNECTION" \
  --set-secrets "DATABASE_URL=$DB_URL_SECRET:latest"

echo
echo "Deployed. Fetching public URL:"
gcloud run services describe "$SERVICE_NAME" --project "$PROJECT_ID" --region "$REGION" --format="value(status.url)"

echo
echo "Verify with: curl <URL>/health"
echo "Remember: build the cloud-target APK with --dart-define=API_BASE_URL=<URL> (docs/CLAUDE.md § Commands)."
