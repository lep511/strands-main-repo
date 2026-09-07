#!/bin/bash
# Deploy a Strands agent to Lambda (Chapters 2-5)
# Usage: ./scripts/deploy-agent.sh <agent-name>
# Example: ./scripts/deploy-agent.sh account-data-loader

AGENT=$1
PROJECT=${PROJECT_NAME:-strands-loan}
ENV=${ENVIRONMENT:-workshop}
REGION=${AWS_DEFAULT_REGION:-us-east-1}
LAYER_NAME="${PROJECT}-${ENV}-strands-sdk"

if [ -z "$AGENT" ]; then
    echo "Usage: $0 <agent-name>"
    echo ""
    echo "Available agents:"
    echo "  account-data-loader    (Chapter 2)"
    echo "  eligibility-filter     (Chapter 3)"
    echo "  loan-product-matcher   (Chapter 4)"
    echo "  risk-assessment        (Chapter 5)"
    echo "  approval-decision      (Chapter 5)"
    exit 1
fi

# Normalize: accept both hyphens and underscores, convert to the canonical form for each
AGENT="$(echo $AGENT | tr '_' '-')"
AGENT_DIR="agents/$(echo $AGENT | tr '-' '_')"
FUNCTION_NAME="${PROJECT}-${ENV}-${AGENT}"

echo "📦 Deploying: ${FUNCTION_NAME}"
echo ""

# Check agent code exists
if [ ! -f "${AGENT_DIR}/main.py" ]; then
    echo "❌ Agent code not found: ${AGENT_DIR}/main.py"
    echo ""
    echo "   Make sure you're running this from ~/workshop/"
    echo "   and the file exists at: ~/workshop/${AGENT_DIR}/main.py"
    exit 1
fi

echo "   📄 Agent code: ${AGENT_DIR}/main.py"

# Get the existing layer ARN (created by CloudFormation)
echo "   🔍 Looking up Strands SDK layer..."
LAYER_ARN=$(aws lambda list-layer-versions \
    --layer-name "$LAYER_NAME" \
    --region "$REGION" \
    --query 'LayerVersions[0].LayerVersionArn' \
    --output text 2>&1)

if [ -z "$LAYER_ARN" ] || [ "$LAYER_ARN" = "None" ] || echo "$LAYER_ARN" | grep -q "Error\|error\|Access"; then
    echo "❌ Could not find layer: ${LAYER_NAME}"
    echo "   Error: ${LAYER_ARN}"
    echo ""
    echo "   Make sure the CloudFormation stack is deployed and AWS credentials are set."
    exit 1
fi

echo "   ✅ Layer: ${LAYER_ARN}"

# Package and deploy
echo "   📦 Packaging agent code..."
BUNDLE_DIR="/tmp/${AGENT}-bundle"
rm -rf "$BUNDLE_DIR"
mkdir -p "$BUNDLE_DIR"
cp "${AGENT_DIR}/main.py" "$BUNDLE_DIR/"

if [ -d "${AGENT_DIR}/policies" ]; then
    cp -r "${AGENT_DIR}/policies" "$BUNDLE_DIR/"
    echo "   📄 Included policies/ directory"
fi

# Bundle Cedar authorization deps when a .cedar policy file is present
if ls "${AGENT_DIR}"/policies/*.cedar 1>/dev/null 2>&1; then
    echo "   🔒 Cedar policy detected - bundling authorization deps..."
    CEDAR_TMP="/tmp/cedar-deps-build"
    rm -rf "$CEDAR_TMP"
    mkdir -p "$CEDAR_TMP"
    pip3 install \
        "strands-agents[cedar]>=0.1.0" \
        --platform manylinux2014_x86_64 \
        --implementation cp \
        --python-version 3.12 \
        --only-binary=:all: \
        -t "$CEDAR_TMP" \
        -q --no-cache-dir 2>&1
    cp -r "$CEDAR_TMP/strands" "$BUNDLE_DIR/"
    cp -r "$CEDAR_TMP/cedarpy" "$BUNDLE_DIR/"
    cp -r "$CEDAR_TMP/cedar_mcp_schema_generator" "$BUNDLE_DIR/"
    echo "   ✅ Cedar deps bundled (strands, cedarpy, cedar_mcp_schema_generator)"
fi

cd "$BUNDLE_DIR"
if ! zip -r "/tmp/${AGENT}.zip" . -q; then
    echo "❌ Failed to create zip"
    exit 1
fi
cd - > /dev/null

echo "   ⬆️  Uploading to Lambda..."
if ! aws lambda update-function-code \
    --function-name "$FUNCTION_NAME" \
    --zip-file "fileb:///tmp/${AGENT}.zip" \
    --region "$REGION" \
    --output text --query 'FunctionName' > /dev/null 2>&1; then
    echo "❌ Failed to update function code for: ${FUNCTION_NAME}"
    echo "   Check that the Lambda function exists and your IAM permissions are correct."
    exit 1
fi

echo "   ⏳ Waiting for code update to complete..."
aws lambda wait function-updated \
    --function-name "$FUNCTION_NAME" \
    --region "$REGION"

echo "   ⚙️  Updating configuration (handler + layer)..."
if ! aws lambda update-function-configuration \
    --function-name "$FUNCTION_NAME" \
    --handler "main.handler" \
    --layers "$LAYER_ARN" \
    --region "$REGION" \
    --output text --query 'FunctionName' > /dev/null 2>&1; then
    echo "❌ Failed to update function configuration"
    exit 1
fi

echo "   ⏳ Waiting for configuration update to complete..."
aws lambda wait function-updated \
    --function-name "$FUNCTION_NAME" \
    --region "$REGION"

echo ""
echo "✅ Agent deployed: ${FUNCTION_NAME}"
echo ""
echo "📊 Check CloudWatch logs (your real agent is now running):"
echo "   Log group: /aws/lambda/${FUNCTION_NAME}"
echo ""
echo "🧪 Test in Kiro:"
echo "   /clear"
echo "   Using our MCP server, process a loan application for Sarah Johnson."
