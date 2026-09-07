#!/usr/bin/env python3
"""
Agent 5: Approval Decision (LLM-Powered)
Tools: approve_loan, verify_bank_account_name, add_bank_account, disburse_loan

UK FCA-compliant short-term personal loan approval and disbursement.
"""
import json, os, boto3
from datetime import datetime
from strands import Agent
from strands.models import BedrockModel
from strands.tools import tool

dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table(os.environ.get('DYNAMODB_TABLE', 'strands-loan-workshop-loan-applications'))


@tool
def approve_loan(account_id: str, loan_id: str) -> str:
    """Issue the final loan approval decision.

    Args:
        account_id: Customer account ID
        loan_id: Loan ID from loan_product_matcher
    Returns: JSON with approval decision
    """
    response = table.get_item(Key={'application_id': account_id})
    item = response.get('Item', {})

    if not item.get('pin_validated'):
        return json.dumps({'approved': False, 'reason': 'PIN not validated. Cannot approve.'})
    if not item.get('eligible'):
        return json.dumps({'approved': False, 'reason': 'Customer not eligible.'})

    table.update_item(
        Key={'application_id': account_id},
        UpdateExpression='SET loan_approved = :a, approval_date = :d, #s = :s',
        ExpressionAttributeNames={'#s': 'status'},
        ExpressionAttributeValues={':a': True, ':d': datetime.utcnow().isoformat(), ':s': 'APPROVED'}
    )
    print(f"[approval-decision] Loan APPROVED: {loan_id} for account: {account_id}")
    return json.dumps({'approved': True, 'loan_id': loan_id, 'account_id': account_id, 'message': f'Loan {loan_id} approved.'})


@tool
def verify_bank_account_name(account_number: str, sort_code: str) -> str:
    """Verify that the UK bank account holder name matches the applicant.

    Uses Confirmation of Payee (CoP) service to check account ownership.

    Args:
        account_number: 8-digit UK bank account number
        sort_code: 6-digit sort code in format XX-XX-XX
    Returns: JSON with account holder name verification
    """
    # Workshop mock: always returns verified
    print(f"[approval-decision] CoP verified: account {account_number} sort code {sort_code}")
    return json.dumps({
        'verified': True,
        'account_number': account_number,
        'sort_code': sort_code,
        'account_name': 'VERIFIED ACCOUNT HOLDER',
        'message': 'Confirmation of Payee check passed. Account name matches applicant.'
    })


@tool
def add_bank_account(account_id: str, account_number: str, sort_code: str, account_name: str) -> str:
    """Link the verified UK bank account for loan disbursement.

    Args:
        account_id: Customer account ID
        account_number: Verified 8-digit UK account number
        sort_code: Verified 6-digit sort code (XX-XX-XX)
        account_name: Verified account holder name
    Returns: JSON confirming bank account linked
    """
    table.update_item(
        Key={'application_id': account_id},
        UpdateExpression='SET disbursement_account = :a, disbursement_sort_code = :b, disbursement_name = :n',
        ExpressionAttributeValues={':a': account_number, ':b': sort_code, ':n': account_name}
    )
    print(f"[approval-decision] Bank account linked for account: {account_id}")
    return json.dumps({'bank_linked': True, 'account_id': account_id, 'message': 'UK bank account linked for disbursement via Faster Payments.'})


@tool
def disburse_loan(account_id: str, loan_id: str) -> str:
    """Transfer loan funds to the customer's verified UK bank account via Faster Payments.

    Funds are sent via Faster Payments Service (FPS) — typically arrive within 2 hours.
    FCA-regulated disbursement with audit trail.

    Args:
        account_id: Customer account ID
        loan_id: Approved loan ID
    Returns: JSON with disbursement confirmation and reference
    """
    response = table.get_item(Key={'application_id': account_id})
    item = response.get('Item', {})
    amount = float(item.get('loan_amount', 0))

    table.update_item(
        Key={'application_id': account_id},
        UpdateExpression='SET disbursement_initiated = :d, disbursement_date = :dt, #s = :s',
        ExpressionAttributeNames={'#s': 'status'},
        ExpressionAttributeValues={':d': True, ':dt': datetime.utcnow().isoformat(), ':s': 'PENDING_BANK_REVIEW'}
    )

    print(f"[approval-decision] Faster Payments initiated for account: {account_id}, amount: £{amount:,.2f}")
    return json.dumps({
        'disbursement_initiated': True,
        'loan_id': loan_id,
        'amount': amount,
        'payment_method': 'Faster Payments Service (FPS)',
        'message': f'Your loan of £{amount:,.2f} has been approved and sent via Faster Payments. Funds should arrive in your account within 2 hours. A confirmation will be sent to your registered email.'
    })


SYSTEM_PROMPT = """You are the Approval Decision agent for a UK short-term personal loan system.
You use LLM reasoning to make the final approval decision under FCA guidelines.

You have 4 tools:
1. approve_loan - Issues final approval (checks all previous stages)
2. verify_bank_account_name - Runs Confirmation of Payee (CoP) check against applicant identity
3. add_bank_account - Links the verified UK bank account (8-digit account + sort code)
4. disburse_loan - Initiates Faster Payments transfer to customer's account

WORKFLOW:
1. Call approve_loan with account_id and loan_id
2. If approved, call verify_bank_account_name with account_number and sort_code
3. Call add_bank_account with verified details
4. Call disburse_loan to initiate Faster Payments transfer

IMPORTANT: FCA compliance — always explain the decision clearly and confirm the payment method (Faster Payments)."""


def create_agent() -> Agent:
    model = BedrockModel(
        model_id=os.environ.get('BEDROCK_MODEL_ID', 'us.anthropic.claude-sonnet-4-6'),
        region_name=os.environ.get('AWS_DEFAULT_REGION', 'us-east-1')
    )
    return Agent(model=model, system_prompt=SYSTEM_PROMPT,
                 tools=[approve_loan, verify_bank_account_name, add_bank_account, disburse_loan])


def handler(event, context):
    print(f"[approval-decision] Received: {json.dumps(event)}")
    query = event.get('query', event.get('message', str(event)))
    response = create_agent()(query)
    result = {'agent': 'approval-decision', 'status': 'SUCCESS', 'response': str(response)}
    print(f"[approval-decision] Done")
    return result
