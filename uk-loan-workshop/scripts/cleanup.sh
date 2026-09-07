#!/bin/bash
# Cleanup all workshop resources including AgentCore Runtime and Gateway
set -e

PROJECT=${PROJECT_NAME:-strands-loan}
ENV=${ENVIRONMENT:-workshop}
REGION=${AWS_DEFAULT_REGION:-us-east-1}
STACK="${PROJECT}-${ENV}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AGENTCORE_DIR="${SCRIPT_DIR}/../agentcore"

echo "🧹 Cleaning up workshop resources: ${STACK}"
echo ""
echo "This will delete:"
echo "  - AgentCore Runtime (LoanOrchestrator)"
echo "  - AgentCore Gateway (LoanProcessingGateway)"
echo "  - S3 deployment bucket (bedrock-agentcore-code-*)"
echo "  - All Lambda agent functions"
echo "  - DynamoDB table (loan application data)"
echo "  - IAM roles"
echo "  - VPC and networking"
echo "  - EC2 code-server instance"
echo ""
read -p "Are you sure? (yes/no): " CONFIRM

if [ "$CONFIRM" != "yes" ]; then
    echo "Cleanup cancelled."
    exit 0
fi

# ─── Step 1: Delete AgentCore Runtime ──────────────────────────────────────
RUNTIME_INFO="${AGENTCORE_DIR}/runtime_info.json"
if [ -f "$RUNTIME_INFO" ]; then
    RUNTIME_ID=$(python3 -c "import json; print(json.load(open('${RUNTIME_INFO}'))['runtime_id'])" 2>/dev/null || true)
    if [ -n "$RUNTIME_ID" ]; then
        echo "🗑️  Deleting AgentCore Runtime: ${RUNTIME_ID}..."
        aws bedrock-agentcore-control delete-agent-runtime \
            --agent-runtime-id "$RUNTIME_ID" \
            --region "$REGION" 2>/dev/null && echo "   ✅ Runtime deleted" || echo "   ⚠️  Runtime not found or already deleted"
        rm -f "$RUNTIME_INFO"
    fi
else
    echo "   ℹ️  No runtime_info.json found — skipping Runtime deletion"
fi

# ─── Step 2: Delete AgentCore Gateway (targets first, then gateway) ──────────
GATEWAY_INFO="${AGENTCORE_DIR}/gateway_info.json"
if [ -f "$GATEWAY_INFO" ]; then
    GATEWAY_ID=$(python3 -c "import json; print(json.load(open('${GATEWAY_INFO}'))['gateway_id'])" 2>/dev/null || true)
    if [ -n "$GATEWAY_ID" ]; then
        echo "🗑️  Deleting AgentCore Gateway targets: ${GATEWAY_ID}..."
        # List and delete all targets
        TARGET_IDS=$(aws bedrock-agentcore-control list-gateway-targets \
            --gateway-identifier "$GATEWAY_ID" \
            --region "$REGION" \
            --query 'gatewayTargets[*].targetId' \
            --output text 2>/dev/null || true)
        for TARGET_ID in $TARGET_IDS; do
            aws bedrock-agentcore-control delete-gateway-target \
                --gateway-identifier "$GATEWAY_ID" \
                --target-id "$TARGET_ID" \
                --region "$REGION" 2>/dev/null && echo "   ✅ Target deleted: ${TARGET_ID}" || true
        done
        echo "🗑️  Deleting AgentCore Gateway: ${GATEWAY_ID}..."
        aws bedrock-agentcore-control delete-gateway \
            --gateway-identifier "$GATEWAY_ID" \
            --region "$REGION" 2>/dev/null && echo "   ✅ Gateway deleted" || echo "   ⚠️  Gateway not found or already deleted"
        rm -f "$GATEWAY_INFO"
    fi
else
    echo "   ℹ️  No gateway_info.json found — skipping Gateway deletion"
fi

# ─── Step 3: Delete S3 deployment bucket ─────────────────────────────────────
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text 2>/dev/null || true)
if [ -n "$ACCOUNT_ID" ]; then
    BUCKET="bedrock-agentcore-code-${ACCOUNT_ID}-${REGION}"
    if aws s3 ls "s3://${BUCKET}" --region "$REGION" &>/dev/null; then
        echo "🗑️  Deleting S3 bucket: ${BUCKET}..."
        aws s3 rb "s3://${BUCKET}" --force --region "$REGION" 2>/dev/null && echo "   ✅ S3 bucket deleted" || echo "   ⚠️  Could not delete bucket"
    else
        echo "   ℹ️  S3 bucket not found — skipping"
    fi
fi

# ─── Step 4: Delete CloudFormation stack ─────────────────────────────────────
echo ""
echo "🗑️  Deleting CloudFormation stack: ${STACK}..."
aws cloudformation delete-stack --stack-name "$STACK" --region "$REGION"

echo "⏳ Waiting for deletion to complete (this takes ~5-10 minutes)..."
aws cloudformation wait stack-delete-complete --stack-name "$STACK" --region "$REGION"

echo ""
echo "✅ All workshop resources deleted successfully."
echo "   No ongoing charges will be incurred."
