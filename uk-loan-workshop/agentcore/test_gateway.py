#!/usr/bin/env python3
"""Test AgentCore Gateway — run after setup_gateway.py"""
import boto3, json, sys

with open('gateway_info.json') as f:
    info = json.load(f)

gateway_id = info['gateway_id']
gateway_url = info['gateway_url']
region = info.get('region', 'us-east-1')

passed = 0

# Test 1: Gateway status
client = boto3.client('bedrock-agentcore-control', region_name=region)
gw = client.get_gateway(gatewayIdentifier=gateway_id)
status = gw['status']
if status == 'READY':
    print(f"✅ Gateway READY: {gateway_id}")
    passed += 1
else:
    print(f"❌ Gateway status: {status}")

# Test 2: All 5 targets present and READY
targets = client.list_gateway_targets(gatewayIdentifier=gateway_id)['items']
expected = {'account-data-loader', 'eligibility-filter', 'loan-product-matcher', 'risk-assessment', 'approval-decision'}
found = {t['name'] for t in targets}
not_ready = [t['name'] for t in targets if t['status'] != 'READY']

if expected == found and not not_ready:
    print(f"✅ All 5 targets READY: {sorted(found)}")
    passed += 1
else:
    missing = expected - found
    if missing: print(f"❌ Missing targets: {missing}")
    if not_ready: print(f"❌ Not READY: {not_ready}")

# Test 3: MCP connection and tool discovery
from strands.tools.mcp.mcp_client import MCPClient
from mcp.client.streamable_http import streamablehttp_client

mcp = MCPClient(lambda: streamablehttp_client(gateway_url))
with mcp:
    tools = mcp.list_tools_sync()
    tool_names = [t.tool_name for t in tools]

if len(tools) == 5:
    print(f"✅ MCP: {len(tools)} tools discovered")
    for name in tool_names:
        print(f"   - {name}")
    passed += 1
else:
    print(f"❌ Expected 5 tools, got {len(tools)}: {tool_names}")

print(f"\n{'✅ Gateway fully operational' if passed == 3 else f'❌ {passed}/3 tests passed'}")
sys.exit(0 if passed == 3 else 1)
