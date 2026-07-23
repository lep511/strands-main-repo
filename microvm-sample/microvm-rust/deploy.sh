#!/bin/bash
set -euo pipefail

# Configuration - update these values
REGION="${AWS_REGION:-us-east-1}"
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
IMAGE_NAME="microvm-rust-app"
MEMORY_MB="${MICROVM_MEMORY_MB:-512}"
BUCKET_NAME="microvm-artifacts-${ACCOUNT_ID}-${REGION}"
BUILD_ROLE_ARN="arn:aws:iam::${ACCOUNT_ID}:role/MicroVMBuildRole"
EXECUTION_ROLE_ARN="arn:aws:iam::${ACCOUNT_ID}:role/MicroVMExecutionRole"

echo "==> Checking S3 bucket..."
if ! aws s3api head-bucket --bucket "${BUCKET_NAME}" 2>/dev/null; then
  read -rp "Bucket '${BUCKET_NAME}' does not exist. Create it? [y/N]: " answer
  if [[ "${answer}" =~ ^[Yy]$ ]]; then
    if [[ "${REGION}" == "us-east-1" ]]; then
      aws s3api create-bucket --bucket "${BUCKET_NAME}" --region "${REGION}"
    else
      aws s3api create-bucket \
        --bucket "${BUCKET_NAME}" \
        --region "${REGION}" \
        --create-bucket-configuration LocationConstraint="${REGION}"
    fi
    echo "    Bucket created: ${BUCKET_NAME}"
  else
    echo "    Aborted. Cannot proceed without the S3 bucket."
    exit 1
  fi
else
  echo "    Bucket already exists: ${BUCKET_NAME}"
fi

echo "==> Packaging artifact..."
zip -r artifact.zip Dockerfile Cargo.toml Cargo.lock src/

echo "==> Uploading to S3..."
aws s3 cp artifact.zip "s3://${BUCKET_NAME}/microvm-images/${IMAGE_NAME}/artifact.zip"

IMAGE_ARN="arn:aws:lambda:${REGION}:${ACCOUNT_ID}:microvm-image:${IMAGE_NAME}"

if aws lambda-microvms get-microvm-image --image-identifier "${IMAGE_ARN}" &>/dev/null; then
  echo "==> Image already exists. Creating new version..."
  echo "    Memory: ${MEMORY_MB} MB"
  aws lambda-microvms update-microvm-image \
    --image-identifier "${IMAGE_ARN}" \
    --base-image-arn "arn:aws:lambda:${REGION}:aws:microvm-image:al2023-1" \
    --build-role-arn "${BUILD_ROLE_ARN}" \
    --code-artifact "{\"uri\":\"s3://${BUCKET_NAME}/microvm-images/${IMAGE_NAME}/artifact.zip\"}" \
    --resources "[{\"minimumMemoryInMiB\":${MEMORY_MB}}]" \
    --hooks '{
      "port": 9000,
      "microvmImageHooks": {
        "ready": "ENABLED",
        "readyTimeoutInSeconds": 120,
        "validate": "ENABLED",
        "validateTimeoutInSeconds": 30
      },
      "microvmHooks": {
        "run": "ENABLED",
        "runTimeoutInSeconds": 5,
        "resume": "ENABLED",
        "resumeTimeoutInSeconds": 5,
        "suspend": "ENABLED",
        "suspendTimeoutInSeconds": 5,
        "terminate": "ENABLED",
        "terminateTimeoutInSeconds": 5
      }
    }'
  echo "==> New version initiated."
else
  echo "==> Creating MicroVM image..."
  echo "    Memory: ${MEMORY_MB} MB"
  aws lambda-microvms create-microvm-image \
    --name "${IMAGE_NAME}" \
    --description "Rust Axum app running on Lambda MicroVM" \
    --base-image-arn "arn:aws:lambda:${REGION}:aws:microvm-image:al2023-1" \
    --build-role-arn "${BUILD_ROLE_ARN}" \
    --code-artifact "{\"uri\":\"s3://${BUCKET_NAME}/microvm-images/${IMAGE_NAME}/artifact.zip\"}" \
    --resources "[{\"minimumMemoryInMiB\":${MEMORY_MB}}]" \
    --hooks '{
      "port": 9000,
      "microvmImageHooks": {
        "ready": "ENABLED",
        "readyTimeoutInSeconds": 120,
        "validate": "ENABLED",
        "validateTimeoutInSeconds": 30
      },
      "microvmHooks": {
        "run": "ENABLED",
        "runTimeoutInSeconds": 5,
        "resume": "ENABLED",
        "resumeTimeoutInSeconds": 5,
        "suspend": "ENABLED",
        "suspendTimeoutInSeconds": 5,
        "terminate": "ENABLED",
        "terminateTimeoutInSeconds": 5
      }
    }'
  echo "==> Image creation initiated."
fi

echo "==> Check status with:"
echo "aws lambda-microvms get-microvm-image --image-identifier ${IMAGE_ARN}"

rm -f artifact.zip
