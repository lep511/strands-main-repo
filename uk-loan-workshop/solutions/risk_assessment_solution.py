#!/usr/bin/env python3
"""
Agent 4: Risk Assessment
Tools: create_pin, validate_pin_for_disbursement
"""
import json, os, hashlib, boto3
from strands import Agent
from strands.models import BedrockModel
from strands.tools import tool

dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table(os.environ.get('DYNAMODB_TABLE', 'strands-loan-workshop-loan-applications'))

@tool
def create_pin(account_id: str, pin: str) -> str:
    """Create a 4-digit transaction PIN for secure disbursement authorization.
    Args:
        account_id: Customer account ID
        pin: 4-digit numeric PIN chosen by customer
    Returns: JSON confirming PIN was created
    """
    if len(pin) != 4 or not pin.isdigit():
        return json.dumps({'pin_created': False, 'error': 'PIN must be exactly 4 digits'})
    
    pin_hash = hashlib.sha256(pin.encode()).hexdigest()
    table.update_item(
        Key={'application_id': account_id},
        UpdateExpression='SET pin_hash = :p, pin_created = :c',
        ExpressionAttributeValues={':p': pin_hash, ':c': True}
    )
    print(f"[risk-assessment] PIN created for account: {account_id}")
    return json.dumps({'pin_created': True, 'account_id': account_id, 'message': 'Transaction PIN created successfully.'})

@tool
def validate_pin_for_disbursement(account_id: str, pin: str) -> str:
    """Validate the transaction PIN before authorizing fund release.
    Args:
        account_id: Customer account ID
        pin: 4-digit PIN to validate
    Returns: JSON with validation result
    """
    response = table.get_item(Key={'application_id': account_id})
    item = response.get('Item', {})
    stored_hash = item.get('pin_hash', '')
    input_hash = hashlib.sha256(pin.encode()).hexdigest()
    
    if stored_hash == input_hash:
        table.update_item(
            Key={'application_id': account_id},
            UpdateExpression='SET pin_validated = :v, #s = :s',
            ExpressionAttributeNames={'#s': 'status'},
            ExpressionAttributeValues={':v': True, ':s': 'PIN_VALIDATED'}
        )
        print(f"[risk-assessment] PIN validated for account: {account_id}")
        return json.dumps({'pin_valid': True, 'account_id': account_id, 'message': 'PIN validated. Authorization granted for disbursement.'})
    
    print(f"[risk-assessment] PIN validation FAILED for account: {account_id}")
    return json.dumps({'pin_valid': False, 'message': 'Invalid PIN. Disbursement not authorized.'})

SYSTEM_PROMPT = """You are the Risk Assessment agent for a nano loan processing system.

Your job is to secure the transaction before disbursement. You have 2 tools:
1. create_pin - Creates a 4-digit transaction PIN
2. validate_pin_for_disbursement - Validates the PIN before fund release

WORKFLOW: Call create_pin first (use "1234" in workshop mode), then validate_pin_for_disbursement.
Both calls need the account_id from previous agents."""

def create_agent() -> Agent:
    model = BedrockModel(model_id=os.environ.get('BEDROCK_MODEL_ID', 'us.anthropic.claude-sonnet-4-6'), region_name=os.environ.get('AWS_DEFAULT_REGION', 'us-east-1'))
    return Agent(model=model, system_prompt=SYSTEM_PROMPT, tools=[create_pin, validate_pin_for_disbursement])

def handler(event, context):
    print(f"[risk-assessment] Received: {json.dumps(event)}")
    query = event.get('query', event.get('message', str(event)))
    response = create_agent()(query)
    result = {'agent': 'risk-assessment', 'status': 'SUCCESS', 'response': str(response)}
    print(f"[risk-assessment] Done")
    return result
