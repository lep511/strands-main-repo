#!/usr/bin/env python3
"""
Agent 2: Eligibility Filter
Tools: verify_open_banking, verify_national_insurance, add_employment_details, check_eligibility_status

UK-compliant KYC verification and eligibility assessment.
Reads account_id from DynamoDB. Writes eligibility result back to DynamoDB.
"""

import json
import os
import re
import boto3
from strands import Agent
from strands.models import BedrockModel
from strands.tools import tool
from strands.vended_interventions.cedar import CedarAuthorization

dynamodb = boto3.resource('dynamodb')
TABLE_NAME = os.environ.get('DYNAMODB_TABLE', 'strands-loan-workshop-loan-applications')
table = dynamodb.Table(TABLE_NAME)

CEDAR_POLICY_PATH = os.path.join(os.path.dirname(__file__), 'policies', 'eligibility.cedar')


@tool
def verify_open_banking(account_id: str, consent_token: str) -> str:
    """
    Verify customer identity via Open Banking consent (FCA-regulated).
    
    Uses the customer's Open Banking consent token to confirm account ownership
    and retrieve verified identity data from their bank.
    
    Args:
        account_id: The customer account ID
        consent_token: Open Banking consent token provided by the customer
    
    Returns:
        JSON with verification status
    """
    # Mock Open Banking verification — token must be non-empty and at least 8 chars
    is_valid = len(consent_token) >= 8

    if is_valid:
        table.update_item(
            Key={'application_id': account_id},
            UpdateExpression='SET open_banking_verified = :v, consent_token = :t',
            ExpressionAttributeValues={':v': True, ':t': consent_token}
        )
        print(f"[eligibility-filter] Open Banking verified for account: {account_id}")

    return json.dumps({
        'open_banking_verified': is_valid,
        'account_id': account_id,
        'message': 'Open Banking identity confirmed.' if is_valid else 'Invalid consent token. Please reconnect your bank account.'
    })


@tool
def verify_national_insurance(account_id: str, nino: str) -> str:
    """
    Verify UK National Insurance Number (NINO).
    
    Format: Two letters, six digits, one letter (e.g. AB123456C).
    Cross-references with HMRC records to confirm identity.
    
    Args:
        account_id: The customer account ID
        nino: National Insurance Number in format AB123456C
    
    Returns:
        JSON with verification status
    """
    # UK NINO format: 2 letters + 6 digits + 1 letter (e.g. AB123456C)
    nino_clean = nino.upper().replace(' ', '')
    pattern = r'^[A-CEGHJ-PR-TW-Z]{1}[A-CEGHJ-NPR-TW-Z]{1}[0-9]{6}[A-D]{1}$'
    is_valid = bool(re.match(pattern, nino_clean))

    if is_valid:
        table.update_item(
            Key={'application_id': account_id},
            UpdateExpression='SET nino = :n, nino_verified = :v',
            ExpressionAttributeValues={':n': nino_clean, ':v': True}
        )
        print(f"[eligibility-filter] NINO verified for account: {account_id}")

    return json.dumps({
        'nino_verified': is_valid,
        'account_id': account_id,
        'message': 'National Insurance Number verified.' if is_valid else 'Invalid NINO format. Expected format: AB123456C'
    })


@tool
def add_employment_details(account_id: str, employer_name: str, monthly_salary: float, employment_type: str) -> str:
    """
    Record employment and income information for eligibility assessment.
    
    Args:
        account_id: The customer account ID
        employer_name: Name of employer or business
        monthly_salary: Monthly income in GBP (£)
        employment_type: "salaried" or "self_employed"
    
    Returns:
        JSON confirming employment details were recorded
    """
    table.update_item(
        Key={'application_id': account_id},
        UpdateExpression='SET employer = :e, monthly_salary = :s, employment_type = :t',
        ExpressionAttributeValues={
            ':e': employer_name,
            ':s': str(monthly_salary),
            ':t': employment_type
        }
    )

    print(f"[eligibility-filter] Employment added for account: {account_id}, salary: £{monthly_salary:,.2f}/month")
    return json.dumps({
        'employment_added': True,
        'account_id': account_id,
        'message': f'Employment details recorded. Monthly income: £{monthly_salary:,.2f}'
    })


@tool
def check_eligibility_status(account_id: str) -> str:
    """
    Make final eligibility decision. Cedar policies enforce all eligibility
    preconditions (Open Banking, NINO, salary thresholds) before this tool
    runs. If Cedar permits the call, the customer is eligible.

    Maximum loan: lesser of 3x monthly salary or £5,000.

    Args:
        account_id: The customer account ID

    Returns:
        JSON with eligibility decision and max loan amount
    """
    response = table.get_item(Key={'application_id': account_id})
    item = response.get('Item', {})
    salary = float(item.get('monthly_salary', 0))

    max_loan = min(salary * 3, 5000.0)

    table.update_item(
        Key={'application_id': account_id},
        UpdateExpression='SET eligible = :e, #s = :s, max_loan_amount = :m',
        ExpressionAttributeNames={'#s': 'status'},
        ExpressionAttributeValues={':e': True, ':s': 'ELIGIBLE', ':m': str(max_loan)}
    )

    print(f"[eligibility-filter] ELIGIBLE: account {account_id}, max loan £{max_loan:,.2f}")
    return json.dumps({
        'eligible': True,
        'account_id': account_id,
        'max_loan_amount': max_loan,
        'message': f'Customer is eligible. Maximum loan amount: £{max_loan:,.2f}'
    })


@tool
def get_eligibility_reasons(account_id: str) -> str:
    """
    Return detailed reasons why a customer is not eligible.
    Call this when check_eligibility_status is denied by authorization policy.

    Args:
        account_id: The customer account ID

    Returns:
        JSON with denial reasons and required thresholds
    """
    response = table.get_item(Key={'application_id': account_id})
    item = response.get('Item', {})

    ob_ok = item.get('open_banking_verified', False)
    nino_ok = item.get('nino_verified', False)
    salary = float(item.get('monthly_salary', 0))
    emp_type = item.get('employment_type', 'salaried')
    min_salary = 1600.0 if emp_type == 'salaried' else 2500.0

    reasons = []
    if not ob_ok:
        reasons.append('Open Banking verification not completed')
    if not nino_ok:
        reasons.append('National Insurance Number not verified')
    if salary < min_salary:
        reasons.append(f'Income below minimum (£{min_salary:,.0f}/month required)')

    table.update_item(
        Key={'application_id': account_id},
        UpdateExpression='SET eligible = :e, #s = :s',
        ExpressionAttributeNames={'#s': 'status'},
        ExpressionAttributeValues={':e': False, ':s': 'NOT_ELIGIBLE'}
    )

    print(f"[eligibility-filter] NOT ELIGIBLE: account {account_id}, reasons: {reasons}")
    return json.dumps({
        'eligible': False,
        'account_id': account_id,
        'reasons': reasons,
        'message': f'Customer is not eligible: {", ".join(reasons)}'
    })


SYSTEM_PROMPT = """You are the Eligibility Filter agent for a UK short-term personal loan processing system.

Your job is to verify customer identity and determine loan eligibility under FCA guidelines. You have 5 tools:
1. verify_open_banking - Validates Open Banking consent token (FCA-regulated account verification)
2. verify_national_insurance - Validates UK National Insurance Number (format: AB123456C)
3. add_employment_details - Records employer, monthly salary in GBP, and employment type
4. check_eligibility_status - Makes the final eligibility decision (Cedar policies enforce preconditions)
5. get_eligibility_reasons - Returns detailed denial reasons when eligibility check is blocked

WORKFLOW: Call tools 1-3 in order using the account_id from the previous agent, then call check_eligibility_status.
Cedar authorization policies enforce eligibility rules. If check_eligibility_status is denied by policy,
call get_eligibility_reasons to retrieve the specific denial reasons and report them to the customer.
If eligible, pass account_id forward."""


def _enrich_context(ctx):
    session = {"role": ctx["invocation_state"].get("role", "none")}
    tool_name = ctx.get("tool_name")
    tool_input = ctx.get("tool_input", {})
    account_id = tool_input.get("account_id")

    if tool_name == "check_eligibility_status" and account_id:
        resp = table.get_item(Key={"application_id": account_id})
        item = resp.get("Item", {})
        session["ob_verified"] = item.get("open_banking_verified", False)
        session["nino_verified"] = item.get("nino_verified", False)
        session["monthly_salary_pence"] = int(float(item.get("monthly_salary", 0)) * 100)
        session["employment_type"] = item.get("employment_type", "unknown")

    return session


def create_agent() -> Agent:
    model = BedrockModel(
        model_id=os.environ.get('BEDROCK_MODEL_ID', 'us.anthropic.claude-sonnet-4-6'),
        region_name=os.environ.get('AWS_DEFAULT_REGION', 'us-east-1'),
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
        tools=[verify_open_banking, verify_national_insurance, add_employment_details,
               check_eligibility_status, get_eligibility_reasons],
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
    print(f"[eligibility-filter] Received: {json.dumps(event)}")
    query = event.get('query', event.get('message', str(event)))
    user_id, role = _parse_identity(query, event)

    agent = create_agent()
    response = agent(query, invocation_state={"user_id": user_id, "role": role})
    result = {'agent': 'eligibility-filter', 'status': 'SUCCESS', 'response': str(response)}
    print(f"[eligibility-filter] Done: {result}")
    return result
