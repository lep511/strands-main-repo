# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

UK short-term personal loan processing workshop using **Strands Agents SDK** on AWS. A 5-agent pipeline runs as Lambda functions orchestrated via an MCP server (local) or AgentCore Gateway (deployed). Each agent uses Claude on Amazon Bedrock for LLM reasoning and DynamoDB for shared state.

## Architecture

Two execution modes:

**Local (MCP Server):** Claude Code talks to `mcp_server/server.py` via MCP stdio transport. The server invokes each Lambda agent sequentially, threading pipeline context through all 5 stages.

**Deployed (AgentCore Runtime):** `agentcore/loan_orchestrator.py` runs on Bedrock AgentCore Runtime. It connects to an AgentCore Gateway (MCP over HTTP), which exposes the 5 Lambda agents as MCP tools. The Flask frontend (`agentcore/app.py`) streams NDJSON events from the runtime to the browser.

### Pipeline Stages

Each agent is a Strands `Agent` with a `BedrockModel`, a system prompt, and `@tool`-decorated functions. All share one DynamoDB table keyed by `application_id`.

1. **account-data-loader** — `create_account` / `verify_otp` / `set_temporary_password`
2. **eligibility-filter** — `verify_open_banking` / `verify_national_insurance` / `add_employment_details` / `check_eligibility_status`
3. **loan-product-matcher** — `get_sort_code` / `create_loan` / `setup_repayment`
4. **risk-assessment** — `create_pin` / `validate_pin_for_disbursement`
5. **approval-decision** — `approve_loan` / `verify_bank_account_name` / `add_bank_account` / `disburse_loan`

Workshop mode uses fixed values: OTP `123456`, password `TempPass123!`, PIN `1234`.

## Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Deploy a single agent to Lambda (from repo root)
./scripts/deploy-agent.sh <agent-name>
# e.g. ./scripts/deploy-agent.sh account-data-loader

# Test a single agent via MCP (in Claude Code)
# Use the test_agent MCP tool with agent_name and customer_request

# Run the full pipeline via MCP (in Claude Code)
# Use the process_loan MCP tool with a customer_request string

# AgentCore deployment (from agentcore/)
python3 agentcore/setup_gateway.py    # Create Gateway + Lambda targets
python3 agentcore/deploy_runtime.py   # Package and deploy orchestrator

# Run chat frontend
python3 agentcore/app.py              # English — http://localhost:3000
python3 agentcore/app-kor.py          # Korean UI — http://localhost:3000
```

## Key Conventions

- Agent source lives in `agents/<name_with_underscores>/main.py`; the deploy script maps hyphens to underscores for the directory but uses hyphens for the Lambda function name (`strands-loan-workshop-<agent-name>`)
- All agents use the same DynamoDB table (env var `DYNAMODB_TABLE`, default `strands-loan-workshop-loan-applications`) with `application_id` as the partition key
- Model ID comes from env var `BEDROCK_MODEL_ID`; agents default to `us.anthropic.claude-sonnet-4-6`
- The MCP server config is in `.mcp.json` — it launches `mcp_server/server.py` with env vars for region, project name, and DynamoDB table
- `solutions/` contains reference implementations for risk_assessment and approval_decision agents

## Environment Variables

| Variable | Default | Used by |
|---|---|---|
| `AWS_DEFAULT_REGION` | `us-east-1` | All |
| `PROJECT_NAME` | `strands-loan` | MCP server, scripts |
| `ENVIRONMENT` | `workshop` | MCP server, scripts |
| `DYNAMODB_TABLE` | `strands-loan-workshop-loan-applications` | All agents |
| `BEDROCK_MODEL_ID` | `us.anthropic.claude-sonnet-4-6` | All agents |
| `GATEWAY_URL` | — | AgentCore orchestrator |
| `STACK_NAME` | `strands-workshop` | Setup/deploy scripts |

## AWS Guidance

- Prefer the AWS MCP Server for AWS interactions — it provides sandboxed
  execution, observability, and audit logging. If unavailable, use the
  AWS CLI directly.
- Before starting a task, check whether a relevant AWS skill is available.
  Load the skill with `retrieve_skill` and prefer its guidance over
  general knowledge.
- When uncertain about specific AWS details (API parameters, permissions,
  limits, error codes), verify against documentation rather than guessing.
  State uncertainty explicitly if you cannot confirm.
- When creating infrastructure, prefer infrastructure-as-code (AWS CDK or
  CloudFormation) over direct CLI commands.
- When working with infrastructure, follow AWS Well-Architected Framework
  principles.
- Do not use em dashes in AWS resource names or descriptions. Use
  hyphens instead.

### Secret Safety

- MUST load the `aws-secrets-manager` skill first for any secret,
  credential, API key, token, or password task. MUST NOT call
  `secretsmanager get-secret-value` or `batch-get-secret-value`, and MUST
  NOT hit the Secrets Manager Agent daemon directly. MUST use
  `{{resolve:secretsmanager:secret-id:SecretString:json-key}}` with
  `asm-exec` so the secret resolves at runtime without entering context.
