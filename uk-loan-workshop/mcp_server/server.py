#!/usr/bin/env python3
"""
MCP Server - Loan Processing Workshop
Connects Claude Code to the 5 Strands Agent pipeline.

Flow: Claude Code → MCP → This server → Lambda agents (1→2→3→4→5)
"""

import json
import os
import boto3
from typing import Any

lambda_client = boto3.client('lambda', region_name=os.environ.get('AWS_DEFAULT_REGION', 'us-east-1'))

PROJECT = os.environ.get('PROJECT_NAME', 'strands-loan')
ENV = os.environ.get('ENVIRONMENT', 'workshop')

AGENT_FUNCTIONS = {
    'account-data-loader': f'{PROJECT}-{ENV}-account-data-loader',
    'eligibility-filter': f'{PROJECT}-{ENV}-eligibility-filter',
    'loan-product-matcher': f'{PROJECT}-{ENV}-loan-product-matcher',
    'risk-assessment': f'{PROJECT}-{ENV}-risk-assessment',
    'approval-decision': f'{PROJECT}-{ENV}-approval-decision',
}


def invoke_agent(agent_name: str, query: str) -> dict:
    """Invoke a single Lambda agent."""
    function_name = AGENT_FUNCTIONS.get(agent_name)
    if not function_name:
        return {'error': f'Unknown agent: {agent_name}'}
    
    print(f"[mcp-server] Invoking {agent_name}: {function_name}")
    
    response = lambda_client.invoke(
        FunctionName=function_name,
        InvocationType='RequestResponse',
        Payload=json.dumps({'query': query, 'message': query})
    )
    
    result = json.loads(response['Payload'].read())
    print(f"[mcp-server] {agent_name} result: {result.get('status', 'unknown')}")
    return result


def process_loan_application(user_message: str) -> str:
    """
    Run the complete 5-agent loan processing pipeline.
    Each agent's result is passed as context to the next.
    """
    print(f"[mcp-server] Starting loan pipeline for: {user_message[:100]}...")
    
    pipeline_context = user_message
    results = {}
    
    # Stage 1: Account Data Loader
    print("[mcp-server] Stage 1: Account Data Loader")
    result1 = invoke_agent('account-data-loader', pipeline_context)
    results['account'] = result1
    
    if result1.get('status') != 'SUCCESS':
        return f"❌ Account creation failed: {result1.get('response', 'Unknown error')}"
    
    account_response = result1.get('response', '')
    pipeline_context = f"{user_message}\n\nAccount Result: {account_response}"
    
    # Stage 2: Eligibility Filter
    print("[mcp-server] Stage 2: Eligibility Filter")
    result2 = invoke_agent('eligibility-filter', pipeline_context)
    results['eligibility'] = result2
    
    eligibility_response = result2.get('response', '')
    if 'NOT ELIGIBLE' in eligibility_response.upper() or 'not eligible' in eligibility_response.lower():
        return f"❌ Eligibility check failed:\n{eligibility_response}"
    
    pipeline_context = f"{pipeline_context}\n\nEligibility Result: {eligibility_response}"
    
    # Stage 3: Loan Product Matcher
    print("[mcp-server] Stage 3: Loan Product Matcher")
    result3 = invoke_agent('loan-product-matcher', pipeline_context)
    results['loan_product'] = result3
    
    loan_response = result3.get('response', '')
    pipeline_context = f"{pipeline_context}\n\nLoan Product Result: {loan_response}"
    
    # Stage 4: Risk Assessment
    print("[mcp-server] Stage 4: Risk Assessment")
    result4 = invoke_agent('risk-assessment', pipeline_context)
    results['risk'] = result4
    
    risk_response = result4.get('response', '')
    pipeline_context = f"{pipeline_context}\n\nRisk Assessment Result: {risk_response}"
    
    # Stage 5: Approval Decision
    print("[mcp-server] Stage 5: Approval Decision")
    result5 = invoke_agent('approval-decision', pipeline_context)
    results['approval'] = result5
    
    approval_response = result5.get('response', '')
    
    # Build final summary
    summary = f"""## Loan Processing Complete

**Stage 1 — Account Created** ✅
{account_response[:200]}...

**Stage 2 — Eligibility Verified** ✅
{eligibility_response[:200]}...

**Stage 3 — Loan Configured** ✅
{loan_response[:200]}...

**Stage 4 — Security Validated** ✅
{risk_response[:200]}...

**Stage 5 — Approval Decision** ✅
{approval_response}
"""
    
    print("[mcp-server] Pipeline complete!")
    return summary


# MCP Server using FastMCP
try:
    from mcp.server.fastmcp import FastMCP
    
    mcp = FastMCP("Loan Processing Workshop")
    
    @mcp.tool()
    def process_loan(customer_request: str) -> str:
        """
        Process a complete nano loan application through all 5 agents.
        
        This tool orchestrates the full loan pipeline:
        1. Account Data Loader - Creates and verifies customer account
        2. Eligibility Filter - KYC verification and eligibility check
        3. Loan Product Matcher - Creates loan and configures repayment
        4. Risk Assessment - PIN creation and validation
        5. Approval Decision - Final approval and bank manager transfer
        
        Args:
            customer_request: Natural language loan request with customer details
            (name, UK phone number, email, Open Banking consent token, National Insurance
            Number (NINO format AB123456C), employment details, loan amount in GBP,
            UK bank account number and sort code)
        
        Returns:
            Complete pipeline results with each stage summary
        """
        return process_loan_application(customer_request)
    
    @mcp.tool()
    def test_agent(agent_name: str, customer_request: str) -> str:
        """
        Test a single agent directly without running the full pipeline.
        Use this to verify your deployed agent works after each chapter.

        Available agents:
        - account-data-loader  (Chapter 2)
        - eligibility-filter   (Chapter 3)
        - loan-product-matcher (Chapter 4)
        - risk-assessment      (Chapter 5)
        - approval-decision    (Chapter 5)

        Args:
            agent_name: Name of the agent to test (e.g. "account-data-loader")
            customer_request: Natural language request with relevant customer details

        Returns:
            The raw response from that single agent only
        """
        result = invoke_agent(agent_name, customer_request)
        if 'error' in result:
            return f"❌ Error: {result['error']}"
        response = result.get('response', str(result))
        return f"## Agent Response: {agent_name}\n\n{response}\n\n✅ Agent ran successfully. Check CloudWatch logs for Bedrock calls."

    @mcp.tool()
    def get_loan_status(account_id: str) -> str:
        """
        Check the current status of a loan application.
        
        Args:
            account_id: The account ID returned when the application was created
        
        Returns:
            Current status and details from DynamoDB
        """
        import boto3
        dynamodb = boto3.resource('dynamodb')
        table = dynamodb.Table(os.environ.get('DYNAMODB_TABLE', 'strands-loan-workshop-loan-applications'))
        
        response = table.get_item(Key={'application_id': account_id})
        item = response.get('Item')
        
        if not item:
            return f"No application found for account ID: {account_id}"
        
        status = item.get('status', 'UNKNOWN')
        name = f"{item.get('first_name', '')} {item.get('last_name', '')}"
        loan_amount = item.get('loan_amount', 'N/A')
        
        return json.dumps({
            'account_id': account_id,
            'customer': name,
            'status': status,
            'loan_amount': loan_amount,
            'eligible': item.get('eligible', False),
            'loan_approved': item.get('loan_approved', False),
        }, indent=2)

except ImportError:
    print("FastMCP not available. Running in Lambda mode.")


def handler(event, context):
    """Lambda handler for MCP Server."""
    print(f"[mcp-server] Event: {json.dumps(event)}")
    
    message = event.get('message', event.get('query', ''))
    if not message:
        return {'error': 'No message provided'}
    
    result = process_loan_application(message)
    return {'statusCode': 200, 'body': result}


if __name__ == '__main__':
    # Run as MCP server via stdio transport
    mcp.run(transport='stdio')
