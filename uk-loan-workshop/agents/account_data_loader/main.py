#!/usr/bin/env python3
"""
Agent 1: Account Data Loader
Tools: create_account, verify_otp, set_temporary_password

Shared state via DynamoDB. CloudWatch logging is automatic via Lambda.
"""

import json
import os
import uuid
import hashlib
from datetime import datetime

import boto3
from strands import Agent
from strands.models import BedrockModel
from strands.tools import tool

dynamodb = boto3.resource('dynamodb')
TABLE_NAME = os.environ.get('DYNAMODB_TABLE', 'strands-loan-workshop-loan-applications')
table = dynamodb.Table(TABLE_NAME)


@tool
def create_account(phone_number: str, email: str, first_name: str, last_name: str) -> str:
    """
    Create a new customer account and send OTP to their email address.
    
    Args:
        phone_number: Customer phone number (e.g. +447911123456)
        email: Customer email for OTP delivery
        first_name: Customer first name
        last_name: Customer last name
    
    Returns:
        JSON with account_id and OTP sent confirmation
    """
    account_id = str(uuid.uuid4())
    otp = "123456"  # Workshop mode: fixed OTP for demo
    
    table.put_item(Item={
        'application_id': account_id,
        'customer_phone': phone_number,
        'email': email,
        'first_name': first_name,
        'last_name': last_name,
        'otp': otp,
        'otp_verified': False,
        'created_at': datetime.utcnow().isoformat(),
        'status': 'PENDING_OTP'
    })
    
    print(f"[account-data-loader] Account created: {account_id} for {email}")
    return json.dumps({
        'account_id': account_id,
        'otp_sent': True,
        'message': f'Account created. OTP sent to {email}.'
    })


@tool
def verify_otp(account_id: str, otp: str) -> str:
    """
    Validate the one-time password sent to the customer's email.
    
    Args:
        account_id: Account ID from create_account
        otp: The 6-digit OTP received by customer
    
    Returns:
        JSON confirming verification status
    """
    response = table.get_item(Key={'application_id': account_id})
    item = response.get('Item')
    
    if not item:
        return json.dumps({'verified': False, 'error': 'Account not found'})
    
    if item.get('otp') == otp:
        table.update_item(
            Key={'application_id': account_id},
            UpdateExpression='SET otp_verified = :v, #s = :s',
            ExpressionAttributeNames={'#s': 'status'},
            ExpressionAttributeValues={':v': True, ':s': 'OTP_VERIFIED'}
        )
        print(f"[account-data-loader] OTP verified for account: {account_id}")
        return json.dumps({'verified': True, 'account_id': account_id, 'message': 'Email verified successfully.'})
    
    return json.dumps({'verified': False, 'message': 'Invalid OTP.'})


@tool
def set_temporary_password(account_id: str, password: str) -> str:
    """
    Set a temporary system password for the new account.
    
    Args:
        account_id: The verified account ID
        password: Temporary password to set
    
    Returns:
        JSON confirming password was set
    """
    password_hash = hashlib.sha256(password.encode()).hexdigest()
    
    table.update_item(
        Key={'application_id': account_id},
        UpdateExpression='SET password_hash = :p, password_set = :ps, #s = :s',
        ExpressionAttributeNames={'#s': 'status'},
        ExpressionAttributeValues={':p': password_hash, ':ps': True, ':s': 'ACCOUNT_READY'}
    )
    
    print(f"[account-data-loader] Password set for account: {account_id}")
    return json.dumps({
        'password_set': True,
        'account_id': account_id,
        'message': 'Account setup complete. Proceeding to eligibility check.'
    })


SYSTEM_PROMPT = """You are the Account Data Loader agent for a UK short-term personal loan processing system.

Your job is to create and verify new customer accounts. You have 3 tools:
1. create_account - Creates account and sends OTP
2. verify_otp - Validates the OTP (use "123456" in workshop mode)
3. set_temporary_password - Completes account setup (use "TempPass123!" in workshop mode)

WORKFLOW: Call all 3 tools in order. Always extract: phone_number, email, first_name, last_name.
Return the account_id so downstream agents can use it."""


def create_agent() -> Agent:
    model = BedrockModel(
        model_id=os.environ.get('BEDROCK_MODEL_ID', 'us.anthropic.claude-sonnet-4-6'),
        region_name=os.environ.get('AWS_DEFAULT_REGION', 'us-east-1'),
    )
    return Agent(model=model, system_prompt=SYSTEM_PROMPT, tools=[create_account, verify_otp, set_temporary_password])


def handler(event, context):
    """Lambda handler."""
    print(f"[account-data-loader] Received: {json.dumps(event)}")
    query = event.get('query', event.get('message', str(event)))
    agent = create_agent()
    response = agent(query)
    result = {'agent': 'account-data-loader', 'status': 'SUCCESS', 'response': str(response)}
    print(f"[account-data-loader] Done: {result}")
    return result
