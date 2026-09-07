#!/usr/bin/env python3
"""
Complete End-to-End Test - AgentCore Gateway Integration
Tests everything from CloudFormation deployment to orchestrator invocation.
"""
import boto3
import json
import sys
import time
import subprocess

STACK_NAME = 'StrandsWorkshop'
REGION = 'us-east-1'

def run_command(cmd, description):
    """Run shell command and return success."""
    print(f"\n→ {description}")
    print(f"  $ {cmd}")
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"  ❌ Failed: {result.stderr}")
        return False
    print(f"  ✓ Success")
    return True

def test_prerequisites():
    """Test 0: Check prerequisites."""
    print("\n" + "="*60)
    print("Test 0: Prerequisites")
    print("="*60)
    
    checks = [
        ("aws --version", "AWS CLI installed"),
        ("python3 --version", "Python 3 installed"),
        ("jq --version", "jq installed")
    ]
    
    for cmd, desc in checks:
        if not run_command(cmd, desc):
            print(f"\n❌ Missing: {desc}")
            print(f"   Install: brew install {cmd.split()[0]}")  # macOS
            return False
    
    # Check Python packages
    try:
        import boto3
        print("  ✓ boto3 installed")
    except ImportError:
        print("  ❌ boto3 not installed")
        print("     Install: pip install boto3")
        return False
    
    return True

def test_cloudformation_deploy():
    """Test 1: Deploy CloudFormation stack."""
    print("\n" + "="*60)
    print("Test 1: CloudFormation Deployment")
    print("="*60)
    
    cfn = boto3.client('cloudformation', region_name=REGION)
    
    # Check if stack exists
    try:
        response = cfn.describe_stacks(StackName=STACK_NAME)
        stack = response['Stacks'][0]
        status = stack['StackStatus']
        
        print(f"✓ Stack exists: {STACK_NAME}")
        print(f"  Status: {status}")
        
        if 'COMPLETE' not in status:
            print(f"  ⚠ Stack not ready (status: {status})")
            return False
        
        # Get outputs
        outputs = {o['OutputKey']: o['OutputValue'] for o in stack.get('Outputs', [])}
        
        required_outputs = [
            'AccountDataLoaderArn',
            'EligibilityFilterArn',
            'LoanProductMatcherArn',
            'RiskAssessmentArn',
            'ApprovalDecisionArn',
            'GatewayRoleArn'
        ]
        
        missing = [o for o in required_outputs if o not in outputs]
        if missing:
            print(f"  ❌ Missing outputs: {missing}")
            return False
        
        print(f"  ✓ All required outputs present")
        return True
        
    except cfn.exceptions.ClientError:
        print(f"❌ Stack not found: {STACK_NAME}")
        print(f"\nDeploy with:")
        print(f"  cd /Users/ifeojo/strands_agent_tools_bootcamp/assets")
        print(f"  aws cloudformation deploy \\")
        print(f"    --template-file strands_workshop.yaml \\")
        print(f"    --stack-name {STACK_NAME} \\")
        print(f"    --capabilities CAPABILITY_IAM \\")
        print(f"    --region {REGION}")
        return False

def test_gateway_setup():
    """Test 2: Create Gateway and add targets."""
    print("\n" + "="*60)
    print("Test 2: Gateway Setup")
    print("="*60)
    
    # Run setup script
    cmd = "cd /Users/ifeojo/strands_agent_tools_bootcamp/assets/workshop/agentcore && python setup_gateway.py"
    
    print("→ Running setup_gateway.py...")
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    
    if result.returncode != 0:
        print(f"❌ Setup failed:")
        print(result.stderr)
        return False
    
    print(result.stdout)
    
    # Verify gateway_info.json was created
    try:
        with open('/Users/ifeojo/strands_agent_tools_bootcamp/assets/workshop/agentcore/gateway_info.json') as f:
            info = json.load(f)
        
        print(f"✓ Gateway created: {info['gateway_id']}")
        print(f"✓ Gateway URL: {info['gateway_url']}")
        print(f"✓ Targets: {len(info['target_ids'])}")
        
        return True
        
    except FileNotFoundError:
        print("❌ gateway_info.json not created")
        return False
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

def test_gateway_ready():
    """Test 3: Wait for Gateway to be READY."""
    print("\n" + "="*60)
    print("Test 3: Gateway Status")
    print("="*60)
    
    try:
        with open('/Users/ifeojo/strands_agent_tools_bootcamp/assets/workshop/agentcore/gateway_info.json') as f:
            info = json.load(f)
        
        gateway_id = info['gateway_id']
        client = boto3.client('bedrock-agentcore-control', region_name=REGION)
        
        print(f"Checking Gateway status: {gateway_id}")
        
        max_attempts = 30
        for attempt in range(max_attempts):
            response = client.get_gateway(gatewayIdentifier=gateway_id)
            status = response['status']
            
            print(f"  Attempt {attempt+1}/{max_attempts}: {status}")
            
            if status == 'READY':
                print(f"✓ Gateway is READY")
                return True
            elif 'FAIL' in status:
                print(f"❌ Gateway failed: {status}")
                return False
            
            time.sleep(10)
        
        print(f"❌ Gateway not ready after {max_attempts} attempts")
        return False
        
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

def test_targets_ready():
    """Test 4: Wait for all targets to be READY."""
    print("\n" + "="*60)
    print("Test 4: Target Status")
    print("="*60)
    
    try:
        with open('/Users/ifeojo/strands_agent_tools_bootcamp/assets/workshop/agentcore/gateway_info.json') as f:
            info = json.load(f)
        
        gateway_id = info['gateway_id']
        client = boto3.client('bedrock-agentcore-control', region_name=REGION)
        
        print(f"Checking target status...")
        
        max_attempts = 30
        for attempt in range(max_attempts):
            response = client.list_gateway_targets(gatewayIdentifier=gateway_id)
            targets = response.get('gatewayTargets', [])
            
            statuses = {t['name']: t['status'] for t in targets}
            
            print(f"\n  Attempt {attempt+1}/{max_attempts}:")
            for name, status in statuses.items():
                print(f"    {name}: {status}")
            
            if all(s == 'READY' for s in statuses.values()):
                print(f"\n✓ All {len(targets)} targets are READY")
                return True
            
            if any('FAIL' in s for s in statuses.values()):
                print(f"\n❌ Some targets failed")
                return False
            
            time.sleep(10)
        
        print(f"\n❌ Targets not ready after {max_attempts} attempts")
        return False
        
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

def test_orchestrator_config():
    """Test 5: Configure orchestrator with Gateway URL."""
    print("\n" + "="*60)
    print("Test 5: Orchestrator Configuration")
    print("="*60)
    
    try:
        with open('/Users/ifeojo/strands_agent_tools_bootcamp/assets/workshop/agentcore/gateway_info.json') as f:
            info = json.load(f)
        
        gateway_url = info['gateway_url']
        
        # Get orchestrator ARN
        cfn = boto3.client('cloudformation', region_name=REGION)
        stack = cfn.describe_stacks(StackName=STACK_NAME)['Stacks'][0]
        outputs = {o['OutputKey']: o['OutputValue'] for o in stack['Outputs']}
        
        orchestrator_arn = outputs.get('LoanOrchestratorArn')
        if not orchestrator_arn:
            print("❌ LoanOrchestratorArn not in stack outputs")
            return False
        
        function_name = orchestrator_arn.split(':')[-1]
        
        # Update Lambda environment
        lambda_client = boto3.client('lambda', region_name=REGION)
        
        print(f"→ Updating {function_name} with Gateway URL")
        
        lambda_client.update_function_configuration(
            FunctionName=function_name,
            Environment={
                'Variables': {
                    'GATEWAY_URL': gateway_url
                }
            }
        )
        
        print(f"✓ Orchestrator configured")
        print(f"  Gateway URL: {gateway_url}")
        
        # Wait for update to complete
        print("→ Waiting for update to complete...")
        time.sleep(5)
        
        return True
        
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

def test_mcp_connection():
    """Test 6: Test MCP connection and tool discovery."""
    print("\n" + "="*60)
    print("Test 6: MCP Connection")
    print("="*60)
    
    try:
        from strands.tools.mcp.mcp_client import MCPClient
        from mcp.client.streamable_http import streamablehttp_client
        
        with open('/Users/ifeojo/strands_agent_tools_bootcamp/assets/workshop/agentcore/gateway_info.json') as f:
            info = json.load(f)
        
        gateway_url = info['gateway_url']
        
        print(f"→ Connecting to Gateway: {gateway_url}")
        
        mcp_client = MCPClient(lambda: streamablehttp_client(gateway_url))
        
        with mcp_client:
            tools = mcp_client.list_tools_sync()
            
            print(f"✓ Connected successfully")
            print(f"✓ Discovered {len(tools)} tools:")
            
            for tool in tools:
                print(f"    - {tool.tool_name}")
            
            if len(tools) >= 5:
                print(f"✓ All expected tools available")
                return True
            else:
                print(f"❌ Expected 5 tools, found {len(tools)}")
                return False
        
    except ImportError:
        print("❌ Missing dependencies")
        print("   Install: pip install strands-agents mcp")
        return False
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

def test_orchestrator_invocation():
    """Test 7: Invoke orchestrator end-to-end."""
    print("\n" + "="*60)
    print("Test 7: Orchestrator Invocation")
    print("="*60)
    
    try:
        # Get orchestrator ARN
        cfn = boto3.client('cloudformation', region_name=REGION)
        stack = cfn.describe_stacks(StackName=STACK_NAME)['Stacks'][0]
        outputs = {o['OutputKey']: o['OutputValue'] for o in stack['Outputs']}
        
        orchestrator_arn = outputs['LoanOrchestratorArn']
        
        # Invoke
        lambda_client = boto3.client('lambda', region_name=REGION)
        
        print(f"→ Invoking orchestrator...")
        
        response = lambda_client.invoke(
            FunctionName=orchestrator_arn,
            InvocationType='RequestResponse',
            Payload=json.dumps({'customer_id': 'TEST123'})
        )
        
        result = json.loads(response['Payload'].read())
        
        print(f"✓ Status Code: {response['StatusCode']}")
        print(f"✓ Response:")
        print(json.dumps(result, indent=2))
        
        if response['StatusCode'] == 200:
            print(f"\n✓ Orchestrator working correctly")
            return True
        else:
            print(f"\n❌ Invocation failed")
            return False
        
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

def main():
    """Run all tests in sequence."""
    print("="*60)
    print("COMPLETE END-TO-END TEST")
    print("AgentCore Gateway Integration")
    print("="*60)
    
    tests = [
        ("Prerequisites", test_prerequisites),
        ("CloudFormation Stack", test_cloudformation_deploy),
        ("Gateway Setup", test_gateway_setup),
        ("Gateway Ready", test_gateway_ready),
        ("Targets Ready", test_targets_ready),
        ("Orchestrator Config", test_orchestrator_config),
        ("MCP Connection", test_mcp_connection),
        ("Orchestrator Invocation", test_orchestrator_invocation)
    ]
    
    results = []
    
    for name, test_func in tests:
        try:
            passed = test_func()
            results.append((name, passed))
            
            if not passed:
                print(f"\n⚠ Test failed: {name}")
                print(f"⚠ Stopping remaining tests")
                break
            
        except KeyboardInterrupt:
            print("\n\nTests interrupted by user")
            sys.exit(1)
        except Exception as e:
            print(f"\n❌ Unexpected error in {name}: {e}")
            results.append((name, False))
            break
    
    # Summary
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)
    
    for name, passed in results:
        status = "✓ PASS" if passed else "❌ FAIL"
        print(f"{status}: {name}")
    
    total = len(results)
    passed_count = sum(1 for _, p in results if p)
    
    print(f"\nTotal: {passed_count}/{total} tests passed")
    
    if passed_count == len(tests):
        print("\n" + "="*60)
        print("🎉 ALL TESTS PASSED!")
        print("="*60)
        print("\nYour AgentCore Gateway integration is fully working.")
        print("\nNext steps:")
        print("  - Test with real customer data")
        print("  - Monitor CloudWatch logs")
        print("  - Deploy to production")
        return 0
    else:
        print("\n" + "="*60)
        print("❌ SOME TESTS FAILED")
        print("="*60)
        print("\nCheck the output above for details.")
        return 1

if __name__ == '__main__':
    sys.exit(main())
