#!/usr/bin/env python3
"""
Agent 4: Risk Assessment
Tools: create_pin, validate_pin_for_disbursement

Security gate before loan disbursement.
"""
import json, os, re, hashlib, boto3
from strands import Agent
from strands.models import BedrockModel
from strands.tools import tool
from strands.vended_interventions.cedar import CedarAuthorization

dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table(os.environ.get('DYNAMODB_TABLE', 'strands-loan-workshop-loan-applications'))

CEDAR_POLICY_PATH = os.path.join(os.path.dirname(__file__), 'policies', 'risk.cedar')


@tool
def create_pin(account_id: str, pin: str) -> str:
    """Create a 4-digit transaction PIN for secure disbursement authorization.

    Args:
        account_id: Customer account ID
        pin: 4-digit numeric PIN
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
    return json.dumps({'pin_created': True, 'account_id': account_id,
                       'message': 'Transaction PIN created successfully.'})


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
        return json.dumps({'pin_valid': True, 'account_id': account_id,
                           'message': 'PIN validated. Authorization granted for disbursement.'})

    print(f"[risk-assessment] PIN validation FAILED for account: {account_id}")
    return json.dumps({'pin_valid': False, 'message': 'Invalid PIN. Disbursement not authorized.'})


SYSTEM_PROMPT = """You are the Risk Assessment agent for a UK short-term personal loan system.

You handle PIN security before loan disbursement. You have 2 tools:
1. create_pin - Creates a 4-digit transaction PIN (stored as SHA-256 hash)
2. validate_pin_for_disbursement - Validates the PIN to authorise fund release

WORKFLOW (handle this automatically — do NOT ask the customer to choose or enter a PIN):
1. Generate a secure 4-digit PIN automatically — use "1234" for the workshop demo
2. Call create_pin with the account_id and the PIN "1234"
3. Immediately call validate_pin_for_disbursement with the same account_id and PIN "1234"
4. If pin_valid=True: confirm disbursement is authorised and tell the customer their account is ready for final approval
5. Do NOT mention manual override. Do NOT ask for user input. PIN setup is fully automated."""


def _enrich_context(ctx):
    session = {"role": ctx["invocation_state"].get("role", "none")}
    tool_name = ctx.get("tool_name")
    tool_input = ctx.get("tool_input", {})
    account_id = tool_input.get("account_id")

    if tool_name == "validate_pin_for_disbursement" and account_id:
        resp = table.get_item(Key={"application_id": account_id})
        item = resp.get("Item", {})
        session["pin_created"] = item.get("pin_created", False)

    return session


def create_agent() -> Agent:
    model = BedrockModel(
        model_id=os.environ.get('BEDROCK_MODEL_ID', 'us.anthropic.claude-sonnet-4-6'),
        region_name=os.environ.get('AWS_DEFAULT_REGION', 'us-east-1')
    )

    cedar = CedarAuthorization(
        policies=CEDAR_POLICY_PATH,
        principal_resolver=lambda state: (
            {"type": "User", "id": state["user_id"]}
            if state.get("user_id") and state["user_id"] != "anonymous"
            else None
        ),
        context_enricher=_enrich_context,
    )

    return Agent(
        model=model,
        system_prompt=SYSTEM_PROMPT,
        tools=[create_pin, validate_pin_for_disbursement],
        interventions=[cedar],
    )


def _parse_identity(text, event):
    """Extract user_id and role from event fields or prompt text."""
    user_id = event.get('user_id')
    role = event.get('role')
    if not user_id:
        m = re.search(r'user_id[=:]\s*(\S+)', text)
        user_id = m.group(1).rstrip(',') if m else 'anonymous'
    if not role:
        m = re.search(r'role[=:]\s*(\S+)', text)
        role = m.group(1).rstrip(',') if m else 'loan_officer'
    return user_id, role


def handler(event, context):
    print(f"[risk-assessment] Received: {json.dumps(event)}")
    query = event.get('query', event.get('message', str(event)))
    user_id, role = _parse_identity(query, event)

    agent = create_agent()
    response = agent(query, invocation_state={"user_id": user_id, "role": role})
    result = {'agent': 'risk-assessment', 'status': 'SUCCESS', 'response': str(response)}
    print(f"[risk-assessment] Done")
    return result
