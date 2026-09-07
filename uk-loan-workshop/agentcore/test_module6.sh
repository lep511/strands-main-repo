#!/bin/bash
# Simplified test - assumes CloudFormation stack already exists (deployed by Workshop Studio)
# This tests ONLY the AgentCore Gateway setup (Module 6)

set -e

STACK_NAME="StrandsWorkshop"
REGION="us-east-1"
AGENTCORE_DIR="/Users/ifeojo/strands_agent_tools_bootcamp/assets/workshop/agentcore"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo "============================================================"
echo "MODULE 6 TEST: AgentCore Gateway Setup"
echo "============================================================"
echo ""
echo "This test assumes CloudFormation stack is already deployed"
echo "(In the workshop, this is done by Workshop Studio)"
echo ""

# Check if stack exists
echo "→ Checking for CloudFormation stack..."
if ! aws cloudformation describe-stacks --stack-name $STACK_NAME --region $REGION >/dev/null 2>&1; then
    echo -e "${RED}❌ Stack $STACK_NAME not found${NC}"
    echo ""
    echo "For testing outside Workshop Studio, you need to:"
    echo "1. Create a simplified CloudFormation stack with:"
    echo "   - 5 Lambda functions (account-data-loader, eligibility-filter, etc.)"
    echo "   - IAM role for AgentCore Gateway"
    echo "   - DynamoDB table"
    echo ""
    echo "Or wait for Workshop Studio deployment in the actual workshop."
    exit 1
fi

echo -e "${GREEN}✓${NC} Stack found: $STACK_NAME"

# Check required outputs
echo ""
echo "→ Verifying stack outputs..."
OUTPUTS=$(aws cloudformation describe-stacks --stack-name $STACK_NAME --region $REGION --query 'Stacks[0].Outputs' --output json)

REQUIRED_OUTPUTS=(
    "AccountDataLoaderArn"
    "EligibilityFilterArn"
    "LoanProductMatcherArn"
    "RiskAssessmentArn"
    "ApprovalDecisionArn"
)

for output in "${REQUIRED_OUTPUTS[@]}"; do
    if echo "$OUTPUTS" | jq -e ".[] | select(.OutputKey==\"$output\")" >/dev/null; then
        echo -e "${GREEN}✓${NC} $output"
    else
        echo -e "${RED}❌${NC} Missing output: $output"
        exit 1
    fi
done

# Check for Gateway role (might not exist in old templates)
if ! echo "$OUTPUTS" | jq -e ".[] | select(.OutputKey==\"GatewayRoleArn\")" >/dev/null; then
    echo -e "${YELLOW}⚠${NC} GatewayRoleArn not found - will need to create IAM role"
    echo ""
    echo "Creating AgentCore Gateway IAM role..."
    
    # Create Gateway role
    ROLE_NAME="AgentCoreGatewayRole"
    
    aws iam create-role \
        --role-name $ROLE_NAME \
        --assume-role-policy-document '{
            "Version": "2012-10-17",
            "Statement": [{
                "Effect": "Allow",
                "Principal": {"Service": "bedrock-agentcore.amazonaws.com"},
                "Action": "sts:AssumeRole"
            }]
        }' \
        --region $REGION 2>/dev/null || echo "Role may already exist"
    
    # Attach Lambda invoke policy
    aws iam put-role-policy \
        --role-name $ROLE_NAME \
        --policy-name LambdaInvokePolicy \
        --policy-document '{
            "Version": "2012-10-17",
            "Statement": [{
                "Effect": "Allow",
                "Action": "lambda:InvokeFunction",
                "Resource": "arn:aws:lambda:'$REGION':*:function:strands-loan-workshop-*"
            }]
        }' \
        --region $REGION
    
    echo -e "${GREEN}✓${NC} Gateway role created"
    
    # Wait for role to propagate
    sleep 10
fi

# Install Python dependencies
echo ""
echo "→ Installing Python dependencies..."
cd "$AGENTCORE_DIR"
pip install -q -r requirements.txt
echo -e "${GREEN}✓${NC} Dependencies installed"

# Run Gateway setup
echo ""
echo "============================================================"
echo "Creating AgentCore Gateway"
echo "============================================================"
python setup_gateway.py

if [ ! -f "gateway_info.json" ]; then
    echo -e "${RED}❌ gateway_info.json not created${NC}"
    exit 1
fi

GATEWAY_ID=$(jq -r '.gateway_id' gateway_info.json)
GATEWAY_URL=$(jq -r '.gateway_url' gateway_info.json)

echo ""
echo -e "${GREEN}✓${NC} Gateway created: $GATEWAY_ID"
echo -e "${GREEN}✓${NC} Gateway URL: $GATEWAY_URL"

# Wait for Gateway to be READY
echo ""
echo "→ Waiting for Gateway to be READY (this may take 2-3 minutes)..."
MAX_ATTEMPTS=30
ATTEMPT=0

while [ $ATTEMPT -lt $MAX_ATTEMPTS ]; do
    STATUS=$(aws bedrock-agentcore-control get-gateway \
        --gateway-identifier "$GATEWAY_ID" \
        --region $REGION \
        --query 'status' \
        --output text 2>/dev/null || echo "UNKNOWN")
    
    if [ "$STATUS" = "READY" ]; then
        echo -e "${GREEN}✓${NC} Gateway is READY"
        break
    elif [[ "$STATUS" == *"FAIL"* ]]; then
        echo -e "${RED}❌ Gateway failed: $STATUS${NC}"
        exit 1
    fi
    
    echo "  Status: $STATUS (attempt $((ATTEMPT+1))/$MAX_ATTEMPTS)"
    ATTEMPT=$((ATTEMPT+1))
    sleep 10
done

if [ $ATTEMPT -eq $MAX_ATTEMPTS ]; then
    echo -e "${RED}❌ Gateway not ready after $MAX_ATTEMPTS attempts${NC}"
    exit 1
fi

# Test MCP connection
echo ""
echo "→ Testing MCP connection..."
python3 << 'EOF'
import sys
try:
    from strands.tools.mcp.mcp_client import MCPClient
    from mcp.client.streamable_http import streamablehttp_client
    import json
    
    with open('gateway_info.json') as f:
        info = json.load(f)
    
    gateway_url = info['gateway_url']
    mcp_client = MCPClient(lambda: streamablehttp_client(gateway_url))
    
    with mcp_client:
        tools = mcp_client.list_tools_sync()
        print(f"✓ Connected to Gateway")
        print(f"✓ Discovered {len(tools)} tools")
        
        if len(tools) >= 5:
            sys.exit(0)
        else:
            print(f"❌ Expected 5 tools, found {len(tools)}")
            sys.exit(1)

except Exception as e:
    print(f"❌ Error: {e}")
    sys.exit(1)
EOF

if [ $? -eq 0 ]; then
    echo ""
    echo "============================================================"
    echo "🎉 MODULE 6 TEST PASSED!"
    echo "============================================================"
    echo ""
    echo "Gateway is ready for the workshop:"
    echo "  Gateway ID: $GATEWAY_ID"
    echo "  Gateway URL: $GATEWAY_URL"
    echo ""
    echo "Next: Configure orchestrator Lambda with Gateway URL"
else
    echo -e "${RED}❌ MCP connection test failed${NC}"
    exit 1
fi
