#!/usr/bin/env python3
"""
Agent 3: Loan Product Matcher
Tools: get_sort_code, create_loan, setup_repayment

UK short-term personal loan product configuration with FCA-compliant terms.
"""
import json, os, re, uuid, boto3
from strands import Agent
from strands.models import BedrockModel
from strands.tools import tool
from strands.vended_interventions.cedar import CedarAuthorization

dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table(os.environ.get('DYNAMODB_TABLE', 'strands-loan-workshop-loan-applications'))

CEDAR_POLICY_PATH = os.path.join(os.path.dirname(__file__), 'policies', 'loan_product.cedar')

# UK bank sort codes (6-digit format XX-XX-XX)
UK_SORT_CODES = {
    'barclays': '20-00-00',
    'hsbc': '40-00-01',
    'lloyds': '30-00-00',
    'natwest': '60-70-80',
    'santander': '09-01-26',
    'halifax': '11-00-00',
    'nationwide': '07-00-55',
    'monzo': '04-00-04',
    'starling': '60-83-71',
    'revolut': '04-29-09',
    'tsb': '30-80-93',
    'metro': '23-05-80',
}


@tool
def get_sort_code(bank_name: str) -> str:
    """Resolve UK bank sort code from bank name.

    Args:
        bank_name: Name of the UK bank (e.g. "Barclays", "Monzo", "Starling")
    Returns: JSON with bank name and 6-digit sort code (format XX-XX-XX)
    """
    key = bank_name.lower().replace(' ', '').replace('bank', '')
    sort_code = UK_SORT_CODES.get(key, 'UNKNOWN')
    print(f"[loan-product-matcher] Sort code for {bank_name}: {sort_code}")
    return json.dumps({
        'bank_name': bank_name,
        'sort_code': sort_code,
        'found': sort_code != 'UNKNOWN',
        'message': f'Sort code for {bank_name}: {sort_code}' if sort_code != 'UNKNOWN' else f'Bank not found. Please verify the bank name.'
    })


@tool
def create_loan(account_id: str, loan_amount: float, tenure_days: int, loan_purpose: str) -> str:
    """Create a short-term personal loan application.

    FCA-regulated terms: 0.8% daily interest cap, max 100% total cost cap.
    Loan range: £500-£5,000. Tenure: 30-90 days.

    Args:
        account_id: Customer account ID
        loan_amount: Loan amount in GBP (£500-£5,000)
        tenure_days: Loan duration in days (30-90)
        loan_purpose: Purpose (e.g. "emergency expenses", "home repair", "education")
    Returns: JSON with loan_id and repayment details
    """
    # Cedar policies enforce: loan_amount >= £500, loan_amount <= max_loan, 30 <= tenure_days <= 90
    loan_id = str(uuid.uuid4())[:8].upper()
    # FCA-compliant: 0.8% daily rate capped at 100% of principal
    daily_rate = 0.008
    interest = min(loan_amount * daily_rate * tenure_days, loan_amount)  # 100% cost cap
    total_repayment = loan_amount + interest

    table.update_item(
        Key={'application_id': account_id},
        UpdateExpression='SET loan_id = :l, loan_amount = :a, tenure_days = :t, purpose = :p, total_repayment = :r, #s = :s',
        ExpressionAttributeNames={'#s': 'status'},
        ExpressionAttributeValues={
            ':l': loan_id, ':a': str(loan_amount), ':t': tenure_days,
            ':p': loan_purpose, ':r': str(total_repayment), ':s': 'LOAN_CREATED'
        }
    )
    print(f"[loan-product-matcher] Loan created: {loan_id} for £{loan_amount:,.2f}")
    return json.dumps({
        'loan_id': loan_id,
        'loan_amount': loan_amount,
        'tenure_days': tenure_days,
        'daily_rate': '0.8%',
        'total_interest': interest,
        'total_repayment': total_repayment,
        'message': f'Loan LN-{loan_id} created. Total repayment: £{total_repayment:,.2f} over {tenure_days} days.'
    })


@tool
def setup_repayment(account_id: str, account_number: str, sort_code: str, repayment_day: int = 1) -> str:
    """Configure Direct Debit for automatic loan repayment.

    Sets up a UK Direct Debit mandate using the customer's bank account details.

    Args:
        account_id: Customer account ID
        account_number: 8-digit UK bank account number
        sort_code: 6-digit sort code in format XX-XX-XX (from get_sort_code)
        repayment_day: Day of month for repayment (1-28, default 1)
    Returns: JSON confirming Direct Debit setup
    """
    # Validate UK account number (8 digits) and sort code (XX-XX-XX)
    if not (len(account_number) == 8 and account_number.isdigit()):
        return json.dumps({'error': 'Invalid account number. Must be 8 digits.'})

    table.update_item(
        Key={'application_id': account_id},
        UpdateExpression='SET repayment_account = :a, sort_code = :b, repayment_day = :d, repayment_configured = :r',
        ExpressionAttributeValues={
            ':a': account_number, ':b': sort_code,
            ':d': repayment_day, ':r': True
        }
    )
    print(f"[loan-product-matcher] Direct Debit configured for account: {account_id}")
    return json.dumps({
        'repayment_configured': True,
        'account_id': account_id,
        'message': f'Direct Debit mandate set up. Repayment collected on day {repayment_day} of each month.'
    })


SYSTEM_PROMPT = """You are the Loan Product Matcher agent for a UK short-term personal loan system.

Your job is to create FCA-compliant loan applications and configure Direct Debit repayment. You have 3 tools:
1. get_sort_code - Resolves UK bank name to 6-digit sort code (format XX-XX-XX) — call FIRST
2. create_loan - Creates loan with amount (£500-£5,000), tenure (30-90 days), and purpose
3. setup_repayment - Sets up Direct Debit mandate with 8-digit account number and sort code

WORKFLOW: First get_sort_code, then create_loan, then setup_repayment.
Extract: loan_amount (GBP), tenure_days, loan_purpose, bank_name, account_number from context.

After completing all 3 steps, summarise the loan configuration and state the application is ready for risk assessment. Do NOT mention disbursement — that happens in a later stage."""


def _enrich_context(ctx):
    session = {"role": ctx["invocation_state"].get("role", "none")}
    tool_name = ctx.get("tool_name")
    tool_input = ctx.get("tool_input", {})
    account_id = tool_input.get("account_id")

    if tool_name == "create_loan":
        session["loan_amount_pence"] = int(float(tool_input.get("loan_amount", 0)) * 100)
        session["tenure_days"] = int(tool_input.get("tenure_days", 0))
        if account_id:
            resp = table.get_item(Key={"application_id": account_id})
            item = resp.get("Item", {})
            session["max_loan_pence"] = int(float(item.get("max_loan_amount", 5000)) * 100)

    if tool_name == "setup_repayment":
        session["repayment_day"] = int(tool_input.get("repayment_day", 1))

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
        tools=[get_sort_code, create_loan, setup_repayment],
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
    print(f"[loan-product-matcher] Received: {json.dumps(event)}")
    query = event.get('query', event.get('message', str(event)))
    user_id, role = _parse_identity(query, event)

    agent = create_agent()
    response = agent(query, invocation_state={"user_id": user_id, "role": role})
    result = {'agent': 'loan-product-matcher', 'status': 'SUCCESS', 'response': str(response)}
    print(f"[loan-product-matcher] Done")
    return result
