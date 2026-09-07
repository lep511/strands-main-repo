#!/bin/bash
set -e

echo "============================================================"
echo "COMPLETE FROM-SCRATCH DEPLOYMENT AND TEST"
echo "AgentCore Gateway Integration"
echo "============================================================"

STACK_NAME="StrandsWorkshop"
REGION="us-east-1"
TEMPLATE_PATH="/Users/ifeojo/strands_agent_tools_bootcamp/assets/strands_workshop.yaml"
AGENTCORE_DIR="/Users/ifeojo/strands_agent_tools_bootcamp/assets/workshop/agentcore"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check prerequisites
echo ""
echo "============================================================"
echo "Step 0: Checking Prerequisites"
echo "============================================================"

command -v aws >/dev/null 2>&1 || { echo -e "${RED}❌ AWS CLI not installed${NC}"; exit 1; }
echo -e "${GREEN}✓${NC} AWS CLI installed"

command -v python3 >/dev/null 2>&1 || { echo -e "${RED}❌ Python 3 not installed${NC}"; exit 1; }
echo -e "${GREEN}✓${NC} Python 3 installed"

command -v jq >/dev/null 2>&1 || { echo -e "${RED}❌ jq not installed${NC}"; exit 1; }
echo -e "${GREEN}✓${NC} jq installed"

# Check and install Python dependencies
if ! python3 -c "import boto3" 2>/dev/null; then
    echo -e "${YELLOW}⚠${NC} Python dependencies not installed"
    echo "→ Installing from requirements.txt..."
    pip install -r "$AGENTCORE_DIR/requirements.txt"
fi

python3 -c "import boto3" 2>/dev/null || { echo -e "${RED}❌ Failed to install boto3${NC}"; exit 1; }
echo -e "${GREEN}✓${NC} Python dependencies installed"

# Check if stack exists and delete if it does
echo ""
echo "============================================================"
echo "Step 1: Cleaning Up Existing Resources"
echo "============================================================"

STACK_EXISTS=$(aws cloudformation describe-stacks --stack-name $STACK_NAME --region $REGION 2>&1)

if echo "$STACK_EXISTS" | grep -q "StackStatus"; then
    echo -e "${YELLOW}⚠${NC} Stack $STACK_NAME already exists"
    read -p "Delete existing stack? (y/n) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        echo "→ Deleting stack..."
        aws cloudformation delete-stack --stack-name $STACK_NAME --region $REGION
        
        echo "→ Waiting for deletion to complete..."
        aws cloudformation wait stack-delete-complete --stack-name $STACK_NAME --region $REGION
        echo -e "${GREEN}✓${NC} Stack deleted"
    else
        echo -e "${YELLOW}⚠${NC} Using existing stack"
    fi
else
    echo -e "${GREEN}✓${NC} No existing stack found"
fi

# Delete existing gateway if it exists
if [ -f "$AGENTCORE_DIR/gateway_info.json" ]; then
    echo ""
    echo "→ Found existing gateway_info.json"
    GATEWAY_ID=$(jq -r '.gateway_id' "$AGENTCORE_DIR/gateway_info.json")
    
    if aws bedrock-agentcore-control get-gateway --gateway-identifier "$GATEWAY_ID" --region $REGION >/dev/null 2>&1; then
        echo "→ Deleting existing Gateway: $GATEWAY_ID"
        aws bedrock-agentcore-control delete-gateway --gateway-identifier "$GATEWAY_ID" --region $REGION
        echo -e "${GREEN}✓${NC} Gateway deleted"
    fi
    
    rm "$AGENTCORE_DIR/gateway_info.json"
    echo -e "${GREEN}✓${NC} Cleaned up gateway_info.json"
fi

# Deploy CloudFormation stack
echo ""
echo "============================================================"
echo "Step 2: Deploying CloudFormation Stack"
echo "============================================================"

if [ ! -f "$TEMPLATE_PATH" ]; then
    echo -e "${RED}❌ Template not found: $TEMPLATE_PATH${NC}"
    exit 1
fi

echo "→ Deploying stack: $STACK_NAME"
echo "  Template: $TEMPLATE_PATH"
echo "  Region: $REGION"

aws cloudformation deploy \
    --template-file "$TEMPLATE_PATH" \
    --stack-name $STACK_NAME \
    --capabilities CAPABILITY_IAM CAPABILITY_NAMED_IAM \
    --region $REGION

echo -e "${GREEN}✓${NC} Stack deployed"

# Wait for stack to be ready
echo ""
echo "→ Waiting for stack to be ready..."
aws cloudformation wait stack-create-complete --stack-name $STACK_NAME --region $REGION 2>/dev/null || \
aws cloudformation wait stack-update-complete --stack-name $STACK_NAME --region $REGION 2>/dev/null || true

echo -e "${GREEN}✓${NC} Stack is ready"

# Verify stack outputs
echo ""
echo "→ Verifying stack outputs..."
OUTPUTS=$(aws cloudformation describe-stacks --stack-name $STACK_NAME --region $REGION --query 'Stacks[0].Outputs' --output json)

REQUIRED_OUTPUTS=(
    "AccountDataLoaderArn"
    "EligibilityFilterArn"
    "LoanProductMatcherArn"
    "RiskAssessmentArn"
    "ApprovalDecisionArn"
    "GatewayRoleArn"
)

for output in "${REQUIRED_OUTPUTS[@]}"; do
    if echo "$OUTPUTS" | jq -e ".[] | select(.OutputKey==\"$output\")" >/dev/null; then
        echo -e "${GREEN}✓${NC} $output"
    else
        echo -e "${RED}❌${NC} Missing output: $output"
        exit 1
    fi
done

# Create Gateway
echo ""
echo "============================================================"
echo "Step 3: Creating AgentCore Gateway"
echo "============================================================"

cd "$AGENTCORE_DIR"

echo "→ Running setup_gateway.py..."
python3 setup_gateway.py

if [ ! -f "gateway_info.json" ]; then
    echo -e "${RED}❌ gateway_info.json not created${NC}"
    exit 1
fi

GATEWAY_ID=$(jq -r '.gateway_id' gateway_info.json)
GATEWAY_URL=$(jq -r '.gateway_url' gateway_info.json)

echo -e "${GREEN}✓${NC} Gateway created: $GATEWAY_ID"
echo -e "${GREEN}✓${NC} Gateway URL: $GATEWAY_URL"

# Wait for Gateway to be READY
echo ""
echo "============================================================"
echo "Step 4: Waiting for Gateway to be READY"
echo "============================================================"

MAX_ATTEMPTS=60
ATTEMPT=0

while [ $ATTEMPT -lt $MAX_ATTEMPTS ]; do
    STATUS=$(aws bedrock-agentcore-control get-gateway \
        --gateway-identifier "$GATEWAY_ID" \
        --region $REGION \
        --query 'status' \
        --output text)
    
    echo "  Attempt $((ATTEMPT+1))/$MAX_ATTEMPTS: $STATUS"
    
    if [ "$STATUS" = "READY" ]; then
        echo -e "${GREEN}✓${NC} Gateway is READY"
        break
    elif [[ "$STATUS" == *"FAIL"* ]]; then
        echo -e "${RED}❌ Gateway failed: $STATUS${NC}"
        exit 1
    fi
    
    ATTEMPT=$((ATTEMPT+1))
    sleep 10
done

if [ $ATTEMPT -eq $MAX_ATTEMPTS ]; then
    echo -e "${RED}❌ Gateway not ready after $MAX_ATTEMPTS attempts${NC}"
    exit 1
fi

# Wait for targets to be READY
echo ""
echo "============================================================"
echo "Step 5: Waiting for Targets to be READY"
echo "============================================================"

ATTEMPT=0

while [ $ATTEMPT -lt $MAX_ATTEMPTS ]; do
    echo ""
    echo "  Attempt $((ATTEMPT+1))/$MAX_ATTEMPTS:"
    
    TARGETS=$(aws bedrock-agentcore-control list-gateway-targets \
        --gateway-identifier "$GATEWAY_ID" \
        --region $REGION \
        --query 'gatewayTargets[*].[name,status]' \
        --output text)
    
    echo "$TARGETS" | while read name status; do
        if [ "$status" = "READY" ]; then
            echo -e "    ${GREEN}✓${NC} $name: $status"
        else
            echo -e "    ${YELLOW}⏳${NC} $name: $status"
        fi
    done
    
    # Check if all are READY
    NOT_READY=$(echo "$TARGETS" | grep -v "READY" | wc -l)
    
    if [ "$NOT_READY" -eq 0 ]; then
        echo ""
        echo -e "${GREEN}✓${NC} All targets are READY"
        break
    fi
    
    ATTEMPT=$((ATTEMPT+1))
    sleep 10
done

if [ $ATTEMPT -eq $MAX_ATTEMPTS ]; then
    echo -e "${RED}❌ Targets not ready after $MAX_ATTEMPTS attempts${NC}"
    exit 1
fi

# Configure orchestrator
echo ""
echo "============================================================"
echo "Step 6: Configuring Orchestrator"
echo "============================================================"

ORCHESTRATOR_ARN=$(aws cloudformation describe-stacks \
    --stack-name $STACK_NAME \
    --region $REGION \
    --query 'Stacks[0].Outputs[?OutputKey==`LoanOrchestratorArn`].OutputValue' \
    --output text)

if [ -z "$ORCHESTRATOR_ARN" ]; then
    echo -e "${RED}❌ LoanOrchestratorArn not found${NC}"
    exit 1
fi

FUNCTION_NAME=$(echo "$ORCHESTRATOR_ARN" | awk -F: '{print $NF}')

echo "→ Updating $FUNCTION_NAME with Gateway URL"

aws lambda update-function-configuration \
    --function-name "$FUNCTION_NAME" \
    --environment "Variables={GATEWAY_URL=$GATEWAY_URL}" \
    --region $REGION >/dev/null

echo -e "${GREEN}✓${NC} Orchestrator configured"

# Wait for update to complete
echo "→ Waiting for update to complete..."
sleep 10

# Test MCP connection
echo ""
echo "============================================================"
echo "Step 7: Testing MCP Connection"
echo "============================================================"

python3 << 'EOF'
import sys
try:
    from strands.tools.mcp.mcp_client import MCPClient
    from mcp.client.streamable_http import streamablehttp_client
    import json
    
    with open('gateway_info.json') as f:
        info = json.load(f)
    
    gateway_url = info['gateway_url']
    print(f"→ Connecting to: {gateway_url}")
    
    mcp_client = MCPClient(lambda: streamablehttp_client(gateway_url))
    
    with mcp_client:
        tools = mcp_client.list_tools_sync()
        print(f"✓ Connected successfully")
        print(f"✓ Discovered {len(tools)} tools:")
        for tool in tools:
            print(f"    - {tool.tool_name}")
        
        if len(tools) >= 5:
            print("✓ All expected tools available")
            sys.exit(0)
        else:
            print(f"❌ Expected 5 tools, found {len(tools)}")
            sys.exit(1)

except ImportError as e:
    print(f"❌ Missing dependencies: {e}")
    print("   Install: pip install strands-agents mcp")
    sys.exit(1)
except Exception as e:
    print(f"❌ Error: {e}")
    sys.exit(1)
EOF

if [ $? -ne 0 ]; then
    echo -e "${RED}❌ MCP connection test failed${NC}"
    exit 1
fi

# Test orchestrator invocation
echo ""
echo "============================================================"
echo "Step 8: Testing Orchestrator Invocation"
echo "============================================================"

echo "→ Invoking orchestrator..."

aws lambda invoke \
    --function-name "$FUNCTION_NAME" \
    --payload '{"customer_id": "TEST123"}' \
    --region $REGION \
    response.json >/dev/null

echo ""
echo "Response:"
cat response.json | jq .
echo ""

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓${NC} Orchestrator invoked successfully"
else
    echo -e "${RED}❌ Orchestrator invocation failed${NC}"
    exit 1
fi

# Success!
echo ""
echo "============================================================"
echo "🎉 ALL TESTS PASSED!"
echo "============================================================"
echo ""
echo "Your AgentCore Gateway integration is fully working!"
echo ""
echo "Resources created:"
echo "  - CloudFormation Stack: $STACK_NAME"
echo "  - Gateway ID: $GATEWAY_ID"
echo "  - Gateway URL: $GATEWAY_URL"
echo "  - 5 Lambda targets (all READY)"
echo "  - Orchestrator configured and tested"
echo ""
echo "Next steps:"
echo "  - Test with real customer data"
echo "  - Monitor CloudWatch logs:"
echo "    aws logs tail /aws/lambda/$FUNCTION_NAME --follow"
echo "  - View Gateway in console:"
echo "    https://console.aws.amazon.com/bedrock/home?region=$REGION#/agentcore/gateways/$GATEWAY_ID"
echo ""
echo "To clean up:"
echo "  aws cloudformation delete-stack --stack-name $STACK_NAME --region $REGION"
echo "  aws bedrock-agentcore-control delete-gateway --gateway-identifier $GATEWAY_ID --region $REGION"
echo ""
