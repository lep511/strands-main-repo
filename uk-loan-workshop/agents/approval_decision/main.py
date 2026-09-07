#!/usr/bin/env python3
"""
Agent 5: Approval Decision (LLM-Powered)
Tools: approve_loan, verify_bank_account_name, add_bank_account, disburse_loan

Final approval and Faster Payments disbursement.
"""

import json
import os
import boto3
from datetime import datetime
from strands import Agent
from strands.models import BedrockModel
from strands.tools import tool

dynamodb = boto3.resource('dynamodb')
TABLE_NAME = os.environ.get('DYNAMODB_TABLE', 'strands-loan-workshop-loan-applications')
table = dynamodb.Table(TABLE_NAME)


@tool
def approve_loan(account_id: str, loan_id: str) -> str:
    """
    Issue the final loan approval decision.
    Requires pin_validated=True and eligible=True in DynamoDB.

    Args:
        account_id: Customer account ID
        loan_id: Loan ID from loan_product_matcher
    Returns: JSON with approval decision
    """
    item = table.get_item(Key={'application_id': account_id}).get('Item', {})

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
    return json.dumps({'approved': True, 'loan_id': loan_id, 'account_id': account_id,
                       'message': f'Loan {loan_id} approved.'})


@tool
def verify_bank_account_name(account_number: str, sort_code: str) -> str:
    """
    Confirmation of Payee (CoP) check — verify account holder name matches applicant.

    Args:
        account_number: 8-digit UK bank account number
        sort_code: Sort code in format XX-XX-XX
    Returns: JSON with CoP verification result
    """
    # Workshop mock: CoP always passes
    print(f"[approval-decision] CoP check: account {account_number}, sort code {sort_code}")
    return json.dumps({
        'verified': True,
        'account_number': account_number,
        'sort_code': sort_code,
        'account_name': 'VERIFIED ACCOUNT HOLDER',
        'message': 'Confirmation of Payee check passed. Account name matches applicant.'
    })


@tool
def add_bank_account(account_id: str, account_number: str, sort_code: str, account_name: str) -> str:
    """
    Link the verified UK bank account for loan disbursement.

    Args:
        account_id: Customer account ID
        account_number: Verified 8-digit UK account number
        sort_code: Verified sort code (XX-XX-XX)
        account_name: Verified account holder name
    Returns: JSON confirming bank account linked
    """
    table.update_item(
        Key={'application_id': account_id},
        UpdateExpression='SET disbursement_account = :a, disbursement_sort_code = :s, disbursement_name = :n',
        ExpressionAttributeValues={':a': account_number, ':s': sort_code, ':n': account_name}
    )
    print(f"[approval-decision] Bank account linked for account: {account_id}")
    return json.dumps({'bank_linked': True, 'account_id': account_id,
                       'message': 'UK bank account linked for disbursement via Faster Payments.'})


@tool
def disburse_loan(account_id: str, loan_id: str) -> str:
    """
    Initiate Faster Payments transfer to customer's verified UK bank account.
    Sets status to PENDING_BANK_REVIEW.

    Args:
        account_id: Customer account ID
        loan_id: Approved loan ID
    Returns: JSON with disbursement confirmation
    """
    item = table.get_item(Key={'application_id': account_id}).get('Item', {})
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
        'message': (
            f'Loan of £{amount:,.2f} approved and submitted via Faster Payments. '
            'Funds typically arrive within 2 hours. A confirmation will be sent to your registered email.'
        )
    })


SYSTEM_PROMPT = """You are the Approval Decision agent for a UK short-term personal loan system.
You use LLM reasoning to make the final approval decision in compliance with FCA guidelines.

You have 4 tools:
1. approve_loan              — Final approval gate: checks pin_validated and eligible flags
2. verify_bank_account_name  — Confirmation of Payee (CoP): verifies account holder matches applicant
3. add_bank_account          — Links the verified UK disbursement account (8-digit number + sort code)
4. disburse_loan             — Initiates Faster Payments transfer; sets status to PENDING_BANK_REVIEW

WORKFLOW:
1. Call approve_loan with account_id and loan_id
2. If approved: call verify_bank_account_name with the customer's account_number and sort_code
3. Call add_bank_account with the verified details
4. Call disburse_loan to initiate the Faster Payments transfer
5. End with a clear summary containing ALL of the following:
   - Loan ID and approved amount
   - Total repayment amount and tenure (days)
   - Payment method: Faster Payments Service (FPS)
   - Direct Debit bank details (bank name, masked account number, sort code) and collection date
   - Final status: PENDING_BANK_REVIEW — funds typically arrive within 2 hours

If approve_loan returns approved=False, stop and explain why the application was declined."""


def create_agent() -> Agent:
    model = BedrockModel(
        model_id=os.environ.get('BEDROCK_MODEL_ID', 'us.anthropic.claude-sonnet-4-6'),
        region_name=os.environ.get('AWS_DEFAULT_REGION', 'us-east-1'),
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
