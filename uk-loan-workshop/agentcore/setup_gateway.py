"""
AgentCore Gateway Setup Script
Creates Gateway and adds Lambda function targets using boto3.

Based on: https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/gateway-add-target-api-target-config.html
"""
import boto3
import json
import os
import sys
import time

STACK_NAME = os.environ.get('STACK_NAME', 'strands-workshop')
REGION = os.environ.get('AWS_REGION', os.environ.get('AWS_DEFAULT_REGION', 'us-east-1'))
PROJECT_NAME = os.environ.get('PROJECT_NAME', 'strands-loan')
ENVIRONMENT = os.environ.get('ENVIRONMENT', 'workshop')


def get_stack_outputs():
    """Get CloudFormation stack outputs."""
    cfn = boto3.client('cloudformation', region_name=REGION)
    print(f"Getting outputs from stack: {STACK_NAME}")
    try:
        stack = cfn.describe_stacks(StackName=STACK_NAME)['Stacks'][0]
        outputs = {o['OutputKey']: o['OutputValue'] for o in stack.get('Outputs', [])}
        return outputs
    except Exception as e:
        print(f"❌ Could not read CloudFormation stack '{STACK_NAME}': {e}")
        print(f"   Make sure the stack exists and you have cloudformation:DescribeStacks permission.")
        sys.exit(1)


def get_gateway_role_arn(outputs):
    """Get gateway role ARN from env var, stack outputs, or construct it."""
    # 1. Explicit env var
    if os.environ.get('GATEWAY_ROLE_ARN'):
        return os.environ['GATEWAY_ROLE_ARN']
    # 2. Stack output
    if outputs.get('GatewayRoleArn'):
        return outputs['GatewayRoleArn']
    # 3. Construct from naming convention
    sts = boto3.client('sts', region_name=REGION)
    account_id = sts.get_caller_identity()['Account']
    constructed = f"arn:aws:iam::{account_id}:role/{PROJECT_NAME}-{ENVIRONMENT}-agentcore-gateway-role"
    print(f"   ⚠️  GatewayRoleArn not in stack outputs, trying constructed: {constructed}")
    return constructed


def get_lambda_arns(outputs):
    """Get Lambda ARNs from stack outputs or construct them."""
    agents = ['account-data-loader', 'eligibility-filter', 'loan-product-matcher',
              'risk-assessment', 'approval-decision']
    
    output_keys = {
        'account-data-loader': 'AccountDataLoaderArn',
        'eligibility-filter': 'EligibilityFilterArn',
        'loan-product-matcher': 'LoanProductMatcherArn',
        'risk-assessment': 'RiskAssessmentArn',
        'approval-decision': 'ApprovalDecisionArn',
    }
    
    arns = {}
    for agent in agents:
        key = output_keys[agent]
        if key in outputs:
            arns[agent] = outputs[key]
        else:
            # Construct from naming convention
            sts = boto3.client('sts', region_name=REGION)
            account_id = sts.get_caller_identity()['Account']
            arns[agent] = f"arn:aws:lambda:{REGION}:{account_id}:function:{PROJECT_NAME}-{ENVIRONMENT}-{agent}"
            print(f"   ⚠️  {key} not in outputs, using: {arns[agent]}")
    
    return arns


def wait_for_gateway(client, gateway_id, max_wait=120):
    """Wait for gateway to become ACTIVE."""
    print(f"   ⏳ Waiting for gateway to become ACTIVE...")
    deadline = time.time() + max_wait
    while time.time() < deadline:
        try:
            resp = client.get_gateway(gatewayIdentifier=gateway_id)
            status = resp.get('status', 'UNKNOWN')
            print(f"      Status: {status}")
            if status in ('ACTIVE', 'READY'):
                return True
            if 'FAIL' in status or 'ERROR' in status or 'DELETE' in status:
                print(f"   ❌ Gateway failed: {status}")
                return False
        except Exception as e:
            print(f"      (polling: {e})")
        time.sleep(10)
    print("   ⚠️  Timed out waiting for gateway")
    return False


def create_gateway(client, gateway_name, role_arn):
    """Create AgentCore Gateway with NONE authorizer."""
    # Check if gateway already exists
    try:
        existing = client.list_gateways()
        for gw in existing.get('items', existing.get('gateways', [])):
            if gw.get('name') == gateway_name:
                gw_id = gw['gatewayId']
                gw_url = gw.get('gatewayUrl', '')
                print(f"   ♻️  Gateway already exists: {gw_id}")
                if not gw_url:
                    detail = client.get_gateway(gatewayIdentifier=gw_id)
                    gw_url = detail.get('gatewayUrl', '')
                # Make sure it's ACTIVE before returning
                status = gw.get('status', '')
                if status != 'ACTIVE':
                    wait_for_gateway(client, gw_id)
                    detail = client.get_gateway(gatewayIdentifier=gw_id)
                    gw_url = detail.get('gatewayUrl', gw_url)
                return gw_id, gw_url
    except Exception as e:
        print(f"   (Could not list gateways: {e})")

    print(f"Creating Gateway: {gateway_name}")
    print(f"   Role ARN: {role_arn}")
    
    try:
        response = client.create_gateway(
            name=gateway_name,
            roleArn=role_arn,
            authorizerType='NONE',
            protocolType='MCP'
        )
    except Exception as e:
        print(f"\n❌ create_gateway failed: {e}")
        print(f"\nCommon causes:")
        print(f"  1. Role doesn't exist yet — redeploy the CloudFormation stack")
        print(f"  2. Missing iam:PassRole — your role needs permission to pass '{role_arn}'")
        print(f"  3. boto3 too old — run: pip install --upgrade boto3")
        print(f"  4. Service not available in {REGION}")
        sys.exit(1)
    
    gateway_id = response['gatewayId']
    gateway_url = response.get('gatewayUrl', '')
    
    print(f"✓ Gateway created: {gateway_id}")
    
    # Wait for it to be active before adding targets
    if not gateway_url:
        wait_for_gateway(client, gateway_id)
        detail = client.get_gateway(gatewayIdentifier=gateway_id)
        gateway_url = detail.get('gatewayUrl', '')
    
    print(f"✓ Gateway URL: {gateway_url}")
    
    # Always wait for ACTIVE before returning — targets can't be added during CREATING
    wait_for_gateway(client, gateway_id)
    
    return gateway_id, gateway_url


def add_lambda_target(client, gateway_id, target_name, lambda_arn, tool_schema):
    """Add Lambda function as Gateway target."""
    print(f"Adding Lambda target: {target_name}")
    
    try:
        response = client.create_gateway_target(
            gatewayIdentifier=gateway_id,
            name=target_name,
            targetConfiguration={
                'mcp': {
                    'lambda': {
                        'lambdaArn': lambda_arn,
                        'toolSchema': {
                            'inlinePayload': tool_schema
                        }
                    }
                }
            },
            credentialProviderConfigurations=[
                {
                    'credentialProviderType': 'GATEWAY_IAM_ROLE'
                }
            ]
        )
    except Exception as e:
        print(f"   ❌ Failed to add target '{target_name}': {e}")
        return None
    
    target_id = response['targetId']
    print(f"   ✓ Target added: {target_id}")
    return target_id


def main():
    print("=" * 60)
    print("  AgentCore Gateway Setup — Loan Processing Workshop")
    print("=" * 60)
    
    # Get stack outputs
    outputs = get_stack_outputs()
    
    # Get role and Lambda ARNs
    gateway_role_arn = get_gateway_role_arn(outputs)
    print(f"✅ Gateway Role: {gateway_role_arn}")
    
    lambda_arns = get_lambda_arns(outputs)
    print(f"✅ Found {len(lambda_arns)} Lambda agents")
    
    # Tool schemas for each Lambda
    tool_schemas = {
        'account-data-loader': [{
            'name': 'load_account_data',
            'description': 'Load customer account data for loan application',
            'inputSchema': {
                'type': 'object',
                'properties': {
                    'customer_id': {'type': 'string', 'description': 'Customer identifier'}
                },
                'required': ['customer_id']
            }
        }],
        'eligibility-filter': [{
            'name': 'check_eligibility',
            'description': 'Check customer eligibility for loan products',
            'inputSchema': {
                'type': 'object',
                'properties': {
                    'account_data': {'type': 'object', 'description': 'Customer account data'}
                },
                'required': ['account_data']
            }
        }],
        'loan-product-matcher': [{
            'name': 'match_loan_products',
            'description': 'Match eligible loan products to customer profile',
            'inputSchema': {
                'type': 'object',
                'properties': {
                    'eligibility_results': {'type': 'object', 'description': 'Eligibility check results'}
                },
                'required': ['eligibility_results']
            }
        }],
        'risk-assessment': [{
            'name': 'assess_risk',
            'description': 'Assess risk for matched loan products',
            'inputSchema': {
                'type': 'object',
                'properties': {
                    'matched_products': {'type': 'object', 'description': 'Matched loan products'}
                },
                'required': ['matched_products']
            }
        }],
        'approval-decision': [{
            'name': 'make_approval_decision',
            'description': 'Make final approval decision based on risk assessment',
            'inputSchema': {
                'type': 'object',
                'properties': {
                    'risk_assessment': {'type': 'object', 'description': 'Risk assessment results'}
                },
                'required': ['risk_assessment']
            }
        }]
    }
    
    # Create boto3 client
    try:
        agentcore = boto3.client('bedrock-agentcore-control', region_name=REGION)
    except Exception as e:
        print(f"\n❌ Cannot create bedrock-agentcore-control client: {e}")
        print(f"   Your boto3 may be too old. Run: pip install --upgrade boto3")
        sys.exit(1)
    
    # Create Gateway
    gateway_id, gateway_url = create_gateway(
        agentcore,
        'LoanProcessingGateway',
        gateway_role_arn
    )
    
    # Add Lambda targets
    target_ids = {}
    for target_name, lambda_arn in lambda_arns.items():
        target_id = add_lambda_target(
            agentcore,
            gateway_id,
            target_name,
            lambda_arn,
            tool_schemas[target_name]
        )
        if target_id:
            target_ids[target_name] = target_id
    
    # Save Gateway info
    script_dir = os.path.dirname(os.path.abspath(__file__))
    info_path = os.path.join(script_dir, 'gateway_info.json')
    
    gateway_info = {
        'gateway_id': gateway_id,
        'gateway_url': gateway_url,
        'target_ids': target_ids,
        'region': REGION,
        'stack_name': STACK_NAME,
    }
    
    with open(info_path, 'w') as f:
        json.dump(gateway_info, f, indent=2)
    
    print(f"\n{'=' * 60}")
    print(f"✅ Gateway setup complete!")
    print(f"\n   Gateway ID:  {gateway_id}")
    print(f"   Gateway URL: {gateway_url}")
    print(f"   Targets:     {len(target_ids)}/{len(lambda_arns)}")
    print(f"   Info saved:  {info_path}")
    print(f"\n   Next: python3 deploy_runtime.py")
    print("=" * 60)
    
    return gateway_info


if __name__ == '__main__':
    main()
