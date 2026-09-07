# AgentCore Gateway Deployment

## Overview

This directory contains the Loan Orchestrator agent that uses Amazon Bedrock AgentCore Gateway to coordinate 5 Lambda specialist agents.

**Based on**: [AgentCore Gateway Lambda Integration](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/gateway-add-target-api-target-config.html)

## Architecture

```
Loan Orchestrator (Lambda)
    ↓ (MCP Protocol via MCPClient)
AgentCore Gateway (MCP Server)
    ↓ (Lambda Targets)
├── account-data-loader
├── eligibility-filter
├── loan-product-matcher
├── risk-assessment
└── approval-decision
```

## Prerequisites

- AWS CLI configured
- Python 3.10+
- CloudFormation stack deployed (creates Lambda functions and Gateway IAM role)

Install Python dependencies:
```bash
pip install -r requirements.txt
```

Or manually:
```bash
pip install boto3 strands-agents mcp
```

## Deployment Steps

### 1. Deploy CloudFormation Stack

The CloudFormation template creates:
- 5 Lambda specialist agents
- Gateway IAM service role
- Required permissions

```bash
aws cloudformation deploy \
  --template-file strands_workshop.yaml \
  --stack-name StrandsWorkshop \
  --capabilities CAPABILITY_IAM
```

### 2. Create Gateway and Add Lambda Targets

Run the setup script to create the Gateway using boto3:

```bash
cd workshop/agentcore
python setup_gateway.py
```

This script:
- Creates AgentCore Gateway with NONE authorizer
- Adds all 5 Lambda functions as targets with tool schemas
- Saves Gateway URL to `gateway_info.json`

**Output**:
```
Creating Gateway: LoanProcessingGateway
✓ Gateway created: gw-abc123
✓ Gateway URL: https://gw-abc123.gateway.bedrock-agentcore.us-east-1.amazonaws.com/mcp
Adding Lambda target: account-data-loader
✓ Target added: target-xyz789
...
✓ Gateway setup complete!
```

### 3. Deploy Orchestrator Lambda

The orchestrator Lambda is already created by CloudFormation. Update it with the Gateway URL:

```bash
# Get Gateway URL from setup
GATEWAY_URL=$(jq -r '.gateway_url' gateway_info.json)

# Update orchestrator Lambda environment
aws lambda update-function-configuration \
  --function-name LoanOrchestrator \
  --environment "Variables={GATEWAY_URL=$GATEWAY_URL}"
```

### 4. Test the Orchestrator

```bash
# Invoke orchestrator
aws lambda invoke \
  --function-name LoanOrchestrator \
  --payload '{"customer_id": "C12345"}' \
  response.json

cat response.json
```

## How It Works

1. **Orchestrator receives request** via Lambda invocation
2. **Loads Gateway URL** from `gateway_info.json` or environment variable
3. **Connects to Gateway** using `MCPClient` with `streamablehttp_client`
4. **Gateway exposes Lambda functions** as MCP tools with defined schemas
5. **Orchestrator calls tools** through the Gateway:
   - `load_account_data(customer_id)`
   - `check_eligibility(account_data)`
   - `match_loan_products(eligibility_results)`
   - `assess_risk(matched_products)`
   - `make_approval_decision(risk_assessment)`
6. **Returns synthesized result** to caller

## Gateway Setup (boto3)

The `setup_gateway.py` script uses boto3 to create the Gateway:

```python
import boto3

agentcore = boto3.client('bedrock-agentcore-control')

# Create Gateway
response = agentcore.create_gateway(
    name='LoanProcessingGateway',
    roleArn=gateway_role_arn,
    authorizerType='NONE',
    protocolType='MCP'
)

# Add Lambda target
agentcore.create_gateway_target(
    gatewayIdentifier=gateway_id,
    name='account-data-loader',
    targetConfiguration={
        'mcp': {
            'lambda': {
                'lambdaArn': lambda_arn,
                'toolSchema': {
                    'inlinePayload': [{
                        'name': 'load_account_data',
                        'description': 'Load customer account data',
                        'inputSchema': {...}
                    }]
                }
            }
        }
    },
    credentialProviderConfigurations=[
        {'credentialProviderType': 'GATEWAY_IAM_ROLE'}
    ]
)
```

## Tool Schemas

Each Lambda target requires a tool schema defining its interface:

```json
{
  "name": "load_account_data",
  "description": "Load customer account data for loan application",
  "inputSchema": {
    "type": "object",
    "properties": {
      "customer_id": {
        "type": "string",
        "description": "Customer identifier"
      }
    },
    "required": ["customer_id"]
  }
}
```

## Environment Variables

- `GATEWAY_URL`: AgentCore Gateway MCP endpoint (set by setup script or manually)
- `STACK_NAME`: CloudFormation stack name (default: StrandsWorkshop)
- `AWS_REGION`: AWS region (default: us-east-1)

## Troubleshooting

### Gateway creation fails
Check that the Gateway IAM role exists and has correct permissions:
```bash
aws iam get-role --role-name AgentCoreGatewayRole
```

### Lambda invocation errors
Verify Gateway role has `lambda:InvokeFunction` permission for all 5 Lambda functions.

### MCP connection errors
- Verify Gateway URL is correct in `gateway_info.json`
- Check orchestrator Lambda has `GATEWAY_URL` environment variable set
- Ensure Gateway is in ACTIVE state:
  ```bash
  aws bedrock-agentcore-control get-gateway --gateway-identifier <gateway-id>
  ```

### Tool not found errors
Verify targets were added successfully:
```bash
aws bedrock-agentcore-control list-gateway-targets --gateway-identifier <gateway-id>
```

## References

- [AgentCore Gateway Lambda Integration](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/gateway-add-target-api-target-config.html)
- [Lambda Function Targets](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/gateway-add-target-lambda.html)
- [AgentCore Gateway Quick Start](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/gateway-quick-start.html)
- [Strands MCPClient Documentation](https://strandsagents.com/)
