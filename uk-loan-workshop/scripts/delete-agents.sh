#!/bin/bash
# delete-agents.sh — Revert all 5 agents back to NOT_DEPLOYED placeholder
# Usage: ./scripts/delete-agents.sh [agent-name]
#        ./scripts/delete-agents.sh          (deletes all 5 agents)
#        ./scripts/delete-agents.sh account-data-loader  (single agent)

PROJECT=${PROJECT_NAME:-strands-loan}
ENV=${ENVIRONMENT:-workshop}
REGION=${AWS_DEFAULT_REGION:-us-east-1}

AGENTS=(
  "account-data-loader"
  "eligibility-filter"
  "loan-product-matcher"
  "risk-assessment"
  "approval-decision"
)

PLACEHOLDER='import json
def handler(event, context):
    agent = "%s"
    return {"status": "NOT_DEPLOYED", "agent": agent,
            "message": f"Run ./scripts/deploy-agent.sh {agent} to deploy your Strands agent"}'

delete_agent() {
  local AGENT=$1
  local FUNCTION_NAME="${PROJECT}-${ENV}-${AGENT}"

  echo "🗑️  Resetting: ${FUNCTION_NAME}"

  # Write placeholder code to a temp file
  printf "$PLACEHOLDER" "$AGENT" "$AGENT" > /tmp/placeholder.py
  zip -j /tmp/placeholder.zip /tmp/placeholder.py -q

  # Reset code to placeholder
  aws lambda update-function-code \
    --function-name "$FUNCTION_NAME" \
    --zip-file fileb:///tmp/placeholder.zip \
    --region "$REGION" \
    --output text --query 'FunctionName' > /dev/null 2>&1 || { echo "❌ Failed to reset code for $FUNCTION_NAME"; return 1; }

  aws lambda wait function-updated --function-name "$FUNCTION_NAME" --region "$REGION"

  # Reset handler back to index.handler and remove layer
  aws lambda update-function-configuration \
    --function-name "$FUNCTION_NAME" \
    --handler "index.handler" \
    --layers [] \
    --region "$REGION" \
    --output text --query 'FunctionName' > /dev/null 2>&1 || { echo "❌ Failed to reset config for $FUNCTION_NAME"; return 1; }

  aws lambda wait function-updated --function-name "$FUNCTION_NAME" --region "$REGION"

  echo "✅ Reset: ${FUNCTION_NAME}"
  rm -f /tmp/placeholder.py /tmp/placeholder.zip
}

if [ -n "$1" ]; then
  # Delete single agent
  delete_agent "$1"
else
  # Delete all agents
  echo "🗑️  Resetting all 5 agents to NOT_DEPLOYED state..."
  for AGENT in "${AGENTS[@]}"; do
    delete_agent "$AGENT"
  done
  echo ""
  echo "✅ All agents reset. Run ./scripts/deploy-agent.sh <name> to re-deploy."
fi
