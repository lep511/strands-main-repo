#!/bin/bash
# Check status of all workshop agents
PROJECT=${PROJECT_NAME:-strands-loan}
ENV=${ENVIRONMENT:-workshop}
REGION=${AWS_DEFAULT_REGION:-us-east-1}

echo "📊 Workshop Agent Status"
echo "========================"
echo "Project: ${PROJECT}-${ENV}"
echo ""

AGENTS=("account-data-loader" "eligibility-filter" "loan-product-matcher" "risk-assessment" "approval-decision")

for AGENT in "${AGENTS[@]}"; do
    FUNCTION="${PROJECT}-${ENV}-${AGENT}"
    INFO=$(aws lambda get-function-configuration --function-name "$FUNCTION" --region "$REGION" 2>/dev/null)
    if [ $? -eq 0 ]; then
        STATE=$(echo "$INFO" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('State','?'))")
        UPDATED=$(echo "$INFO" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('LastModified','?')[:10])")
        echo "✅ ${AGENT} — ${STATE} (updated: ${UPDATED})"
    else
        echo "❌ ${AGENT} — NOT FOUND"
    fi
done

echo ""
echo "🗄️  DynamoDB Table:"
TABLE="${PROJECT}-${ENV}-loan-applications"
aws dynamodb describe-table --table-name "$TABLE" --region "$REGION" \
    --query 'Table.{Name:TableName, Status:TableStatus, Items:ItemCount}' \
    --output table 2>/dev/null || echo "   Table not found"
