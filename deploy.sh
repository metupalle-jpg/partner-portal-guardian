#!/usr/bin/env bash
# deploy.sh - Deploy Partner Portal Guardian to Cloud Run + Cloud Scheduler
set -euo pipefail

PROJECT_ID="dave-487819"
REGION="me-central1"
SERVICE_NAME="partner-guardian"
SCHEDULER_JOB="partner-guardian-nightly"
SA_EMAIL="${PROJECT_ID}@appspot.gserviceaccount.com"

echo "=== Step 1: Deploy to Cloud Run from source ==="
gcloud run deploy "${SERVICE_NAME}" \
  --project="${PROJECT_ID}" \
  --region="${REGION}" \
  --source=. \
  --timeout=300 \
  --memory=512Mi \
  --min-instances=0 \
  --max-instances=1 \
  --no-allow-unauthenticated \
  --set-env-vars="GOOGLE_CLOUD_PROJECT=${PROJECT_ID},GOOGLE_CLOUD_LOCATION=${REGION},GOOGLE_GENAI_USE_VERTEXAI=TRUE"

# Get the deployed service URL
SERVICE_URL=$(gcloud run services describe "${SERVICE_NAME}" \
  --project="${PROJECT_ID}" \
  --region="${REGION}" \
  --format='value(status.url)')

echo "=== Deployed to: ${SERVICE_URL} ==="

echo "=== Step 2: Create Cloud Scheduler job (midnight Dubai = 20:00 UTC) ==="
# Delete existing job if present
gcloud scheduler jobs delete "${SCHEDULER_JOB}" \
  --project="${PROJECT_ID}" \
  --location="${REGION}" \
  --quiet 2>/dev/null || true

gcloud scheduler jobs create http "${SCHEDULER_JOB}" \
  --project="${PROJECT_ID}" \
  --location="${REGION}" \
  --schedule="0 0 * * *" \
  --time-zone="Asia/Dubai" \
  --uri="${SERVICE_URL}/run" \
  --http-method=POST \
  --body='{"message":"Nightly health check"}' \
  --oidc-service-account-email="${SA_EMAIL}" \
  --oidc-audience="${SERVICE_URL}" \
  --attempt-deadline=600s

echo "=== Step 3: Grant Cloud Run invoker role to scheduler SA ==="
gcloud run services add-iam-policy-binding "${SERVICE_NAME}" \
  --project="${PROJECT_ID}" \
  --region="${REGION}" \
  --member="serviceAccount:${SA_EMAIL}" \
  --role="roles/run.invoker"

echo ""
echo "============================================="
echo "  DEPLOYMENT COMPLETE"
echo "  Service:   ${SERVICE_URL}"
echo "  Scheduler: ${SCHEDULER_JOB} (daily 00:00 Dubai)"
echo "  Test now:  gcloud scheduler jobs run ${SCHEDULER_JOB} --project=${PROJECT_ID} --location=${REGION}"
echo "============================================="
