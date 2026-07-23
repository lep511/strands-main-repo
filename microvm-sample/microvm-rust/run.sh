#!/bin/bash
set -euo pipefail

# Configuration - update these values
REGION="${AWS_REGION:-us-east-1}"
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
IMAGE_NAME="microvm-rust-app"
EXECUTION_ROLE_ARN="arn:aws:iam::${ACCOUNT_ID}:role/MicroVMExecutionRole"
IMAGE_ARN="arn:aws:lambda:${REGION}:${ACCOUNT_ID}:microvm-image:${IMAGE_NAME}"
IMAGE_VERSION="${1:-$(aws lambda-microvms get-microvm-image \
  --image-identifier "${IMAGE_ARN}" \
  --query 'latestActiveImageVersion' --output text 2>/dev/null || echo "1.0")}"

echo "==> Running MicroVM..."
RESPONSE=$(aws lambda-microvms run-microvm \
  --image-identifier "arn:aws:lambda:${REGION}:${ACCOUNT_ID}:microvm-image:${IMAGE_NAME}" \
  --image-version "${IMAGE_VERSION}" \
  --execution-role-arn "${EXECUTION_ROLE_ARN}" \
  --idle-policy '{
    "maxIdleDurationSeconds": 900,
    "suspendedDurationSeconds": 300,
    "autoResumeEnabled": true
  }' \
  --maximum-duration-in-seconds 28800 \
  --logging "{\"cloudWatch\":{\"logGroup\":\"/aws/lambda-microvms/${IMAGE_NAME}\"}}")

MICROVM_ID=$(echo "$RESPONSE" | jq -r '.microvmId')
ENDPOINT=$(echo "$RESPONSE" | jq -r '.endpoint')

echo "==> MicroVM started!"
echo "    ID:       ${MICROVM_ID}"
echo "    Endpoint: ${ENDPOINT}"
echo ""
echo "==> To authenticate and call:"
echo "TOKEN=\$(aws lambda-microvms create-microvm-auth-token \\"
echo "  --microvm-identifier ${MICROVM_ID} \\"
echo "  --expiration-in-minutes 30 \\"
echo "  --allowed-ports '[{\"port\":8080}]' \\"
echo "  --query 'authToken.\"X-aws-proxy-auth\"' --output text)"
echo ""
echo "curl \"https://${ENDPOINT}/\" -H \"X-aws-proxy-auth: \$TOKEN\""
