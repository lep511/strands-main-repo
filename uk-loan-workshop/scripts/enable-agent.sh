#!/bin/bash
# Enable a pre-built agent Lambda function (Chapters 2-4)
# Usage: ./scripts/enable-agent.sh <agent-name>
# Example: ./scripts/enable-agent.sh account-data-loader

set -e

AGENT=$1
PROJECT=${PROJECT_NAME:-strands-loan}
ENV=${ENVIRONMENT:-workshop}
REGION=${AWS_DEFAULT_REGION:-us-east-1}

if [ -z "$AGENT" ]; then
    echo "Usage: $0 <agent-name>"
    echo "Available agents:"
    echo "  account-data-loader    (Chapter 2)"
    echo "  eligibility-filter     (Chapter 3)"
    echo "  loan-product-matcher   (Chapter 4)"
    echo "  risk-assessment        (Chapter 5 - build yourself)"
    echo "  approval-decision      (Chapter 5 - build yourself)"
    exit 1
fi

FUNCTION_NAME="${PROJECT}-${ENV}-${AGENT}"

echo "🚀 Enabling agent: ${FUNCTION_NAME}"
echo "   Region: ${REGION}"
echo ""

# Check function exists
if ! aws lambda get-function --function-name "$FUNCTION_NAME" --region "$REGION" &>/dev/null; then
    echo "❌ Function not found: ${FUNCTION_NAME}"
    echo "   Make sure the CloudFormation stack is deployed first."
    exit 1
fi

# Remove any throttle (set concurrency to unreserved)
aws lambda delete-function-concurrency \
    --function-name "$FUNCTION_NAME" \
    --region "$REGION" 2>/dev/null || true

echo "✅ Agent enabled: ${FUNCTION_NAME}"
echo ""
echo "📊 Check CloudWatch logs:"
echo "   Log group: /aws/lambda/${FUNCTION_NAME}"
echo "   Or use 'Chapter $(echo $AGENT | grep -o '[0-9]' | head -1) - CWLI' saved query"
echo ""
echo "🧪 Test with Claude Code:"
echo "   let's use our mcp to start a loan application"
