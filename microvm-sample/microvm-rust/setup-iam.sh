#!/bin/bash
set -euo pipefail

REGION="${AWS_REGION:-us-east-1}"
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
BUCKET_NAME="microvm-artifacts-${ACCOUNT_ID}-${REGION}"

echo "==> Account: ${ACCOUNT_ID}"
echo "==> Region:  ${REGION}"
echo ""

# --- Build Role ---
BUILD_ROLE_NAME="MicroVMBuildRole"

if aws iam get-role --role-name "${BUILD_ROLE_NAME}" &>/dev/null; then
  echo "==> Role '${BUILD_ROLE_NAME}' already exists, skipping."
else
  echo "==> Creating role '${BUILD_ROLE_NAME}'..."

  aws iam create-role \
    --role-name "${BUILD_ROLE_NAME}" \
    --assume-role-policy-document "$(cat <<EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": { "Service": "lambda.amazonaws.com" },
      "Action": "sts:AssumeRole",
      "Condition": {
        "StringEquals": {
          "aws:SourceAccount": "${ACCOUNT_ID}"
        }
      }
    }
  ]
}
EOF
)"

  aws iam put-role-policy \
    --role-name "${BUILD_ROLE_NAME}" \
    --policy-name "MicroVMBuildPolicy" \
    --policy-document "$(cat <<EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": "s3:GetObject",
      "Resource": "arn:aws:s3:::${BUCKET_NAME}/microvm-images/*"
    },
    {
      "Effect": "Allow",
      "Action": [
        "logs:CreateLogGroup",
        "logs:CreateLogStream",
        "logs:PutLogEvents"
      ],
      "Resource": "arn:aws:logs:${REGION}:${ACCOUNT_ID}:log-group:/aws/lambda-microvms/*"
    }
  ]
}
EOF
)"

  echo "    Created with S3 read + CloudWatch Logs permissions."
fi

echo ""

# --- Execution Role ---
EXEC_ROLE_NAME="MicroVMExecutionRole"

if aws iam get-role --role-name "${EXEC_ROLE_NAME}" &>/dev/null; then
  echo "==> Role '${EXEC_ROLE_NAME}' already exists, skipping."
else
  echo "==> Creating role '${EXEC_ROLE_NAME}'..."

  aws iam create-role \
    --role-name "${EXEC_ROLE_NAME}" \
    --assume-role-policy-document "$(cat <<EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": { "Service": "lambda.amazonaws.com" },
      "Action": "sts:AssumeRole",
      "Condition": {
        "StringEquals": {
          "aws:SourceAccount": "${ACCOUNT_ID}"
        }
      }
    }
  ]
}
EOF
)"

  aws iam put-role-policy \
    --role-name "${EXEC_ROLE_NAME}" \
    --policy-name "MicroVMExecutionPolicy" \
    --policy-document "$(cat <<EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "logs:CreateLogGroup",
        "logs:CreateLogStream",
        "logs:PutLogEvents"
      ],
      "Resource": "arn:aws:logs:${REGION}:${ACCOUNT_ID}:log-group:/aws/lambda-microvms/*"
    }
  ]
}
EOF
)"

  echo "    Created with CloudWatch Logs permissions."
fi

echo ""
echo "==> Done. Wait ~10 seconds for IAM propagation before running deploy.sh."
