## The UK Short-Term Loan Processing System

Traditional loan applications can take 30-45 minutes to complete, with customers navigating multiple screens for identity checks, affordability assessments and document uploads. Multi-agent AI collapses this into a single conversation where each agent handles a specific FCA-regulated step, all coordinated automatically.

Here's the complete system architecture we'll build throughout this workshop:

![Complete system architecture diagram](public/architecture-updated.png)

Complete system architecture diagram

## Key Technologies

- **[Amazon Bedrock](https://aws.amazon.com/bedrock/)** — Claude Sonnet 4.6 for LLM intelligence in the Approval Decision agent ([Bedrock User Guide](https://docs.aws.amazon.com/bedrock/latest/userguide/) )
- **[Amazon Bedrock AgentCore](https://aws.amazon.com/bedrock/agentcore/)** — Production orchestration platform with session isolation, streaming, and extended execution (Chapter 6)
- **[Strands SDK](https://strandsagents.com/)** — Agent framework with Bedrock model integration
- **[MCP Protocol](https://docs.anthropic.com/en/docs/agents-and-tools/mcp)** — Model Context Protocol for [Kiro CLI](https://kiro.dev/docs/cli/) integration, connects your terminal directly to the agent network
- **[AWS Lambda](https://aws.amazon.com/lambda/)** — Serverless agent deployment with automatic scaling ([Lambda Developer Guide](https://docs.aws.amazon.com/lambda/latest/dg/) )
- **[Amazon DynamoDB](https://aws.amazon.com/dynamodb/)** — Shared state across the 5-agent pipeline ([DynamoDB Developer Guide](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/) )
- **[Amazon CloudWatch](https://aws.amazon.com/cloudwatch/)** — Logging and monitoring for all Lambda functions ([CloudWatch User Guide](https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/) )

## UK Financial Standards

This workshop uses FCA-regulated UK financial concepts throughout:

| Concept | UK Standard | Description |
| --- | --- | --- |
| Identity verification | **Open Banking** (FCA-regulated) | Customer authorises access via consent token |
| Government ID | **NINO** (National Insurance Number) | Format: `AB123456C` — verified against HMRC |
| Bank routing | **Sort Code** (6-digit `XX-XX-XX`) | e.g. Barclays `20-00-00`, Monzo `04-00-04` |
| Account number | **8-digit account number** | UK standard (replaces 10-digit NUBAN) |
| Payment transfer | **Faster Payments Service (FPS)** | Arrives within 2 hours |
| Identity check | **Confirmation of Payee (CoP)** | Verifies account name matches applicant |
| Currency | **GBP (£)** | Loan range £500–£5,000 |
| Interest rate cap | **0.8% per day** | FCA short-term credit cap |
| Total cost cap | **100% of principal** | FCA consumer protection rule |

## Why Multi-Agent Architecture?

Before diving into the pipeline, let's understand why we split this into 5 agents instead of one large LLM agent.

**Cost Efficiency**

- Deterministic validation (Agents 1-3): $0 per check
- LLM-only approach: High token costs for simple rule enforcement
- **Pattern**: Use code for rules, LLMs for reasoning (Agent 5 only)

**Speed & Reliability**

- API validation: 200ms response time
- LLM parsing and validation: 2-3 seconds + hallucination risk
- **Pattern**: Deterministic gates prevent errors and reduce latency

**Compliance & Control**

- Hard gates enforce FCA regulatory requirements
- LLMs might "be helpful" and bypass mandatory checks
- **Pattern**: Separate validation (Agents 2-3) from decision-making (Agent 5)

**Real-World Impact**

- 30-40% cost reduction vs LLM-only approach
- 60% faster processing for deterministic steps
- 0% false positives on eligibility checks

---

## The 5-Agent Pipeline

Each agent in the pipeline owns one stage of the customer loan journey:

| Stage | Agent | Tools | Output |
| --- | --- | --- | --- |
| 1️⃣ | **Account Data Loader** | `create_account` `verify_otp` `set_temporary_password` | `account_id` verified ✅ |
| 2️⃣ | **Eligibility Filter** | `verify_open_banking` `verify_national_insurance` `add_employment_details` `check_eligibility_status` | `eligible=true` (or ❌ STOP) |
| 3️⃣ | **Loan Product Matcher** | `get_sort_code` `create_loan` `setup_repayment` | `loan_id` configured ✅ |
| 4️⃣ | **Risk Assessment** | `create_pin` `validate_pin_for_disbursement` | `pin_validated=true` ✅ |
| 5️⃣ | **Approval Decision** *(LLM)* | `approve_loan` `verify_bank_account_name` `add_bank_account` `disburse_loan` | APPROVED → Faster Payments ✅ |

> **Stage 2 is a hard gate.** If the customer is not eligible (income below £1,600/month, or identity checks fail), the pipeline stops immediately — no further agents are called, no resources wasted.

## Complete Tool Reference

| Agent | Tool | Description |
| --- | --- | --- |
| **1\. Account Data Loader** | `create_account` | Create account, trigger OTP to email |
|  | `verify_otp` | Validate email OTP (workshop: `123456`) |
|  | `set_temporary_password` | Set system credentials |
| **2\. Eligibility Filter** | `verify_open_banking` | FCA Open Banking consent verification |
|  | `verify_national_insurance` | UK NINO check (format `AB123456C`) |
|  | `add_employment_details` | Monthly income in GBP, employer, employment type |
|  | `check_eligibility_status` | Final decision (min £1,600 salaried / £2,500 self-employed) |
| **3\. Loan Product Matcher** | `get_sort_code` | Resolve UK bank name to sort code (`XX-XX-XX`) |
|  | `create_loan` | Create loan (£500–£5,000, 30–90 days, 0.8%/day FCA cap) |
|  | `setup_repayment` | Configure Direct Debit mandate |
| **4\. Risk Assessment** | `create_pin` | Create 4-digit transaction PIN |
|  | `validate_pin_for_disbursement` | Validate PIN before fund release |
| **5\. Approval Decision** | `approve_loan` | Final loan approval |
|  | `verify_bank_account_name` | Confirmation of Payee (CoP) check |
|  | `add_bank_account` | Link UK account (8-digit + sort code) |
|  | `disburse_loan` | Transfer via Faster Payments Service |

## Architecture: MCP Server + Lambda Agents

```
Kiro CLI → MCP Server (local server.py, stdio) → 5 Agent Lambdas → DynamoDB/Bedrock
```

The **MCP Server** (`mcp_server/server.py`) runs as a **local Python process** on the EC2 instance, launched by kiro-cli via stdio. It:

1. Receives tool calls from Kiro CLI via the MCP protocol
2. Calls each agent Lambda in sequence
3. Passes context between agents
4. Returns the final result to Kiro CLI

## Why MCP (Model Context Protocol)?

**MCP is a standard protocol that lets AI assistants (like Kiro CLI) discover and use tools.** Instead of hardcoding how to call your Lambda functions, MCP provides a standard interface.

**How it works in this workshop:**

1. **Kiro CLI** asks: "What tools are available?"
2. **MCP Server** responds: "I have 3 tools: `process_loan` (runs all 5 agents), `test_agent` (test one agent), `get_loan_status` (check DynamoDB)"
3. **Kiro CLI** calls: "Use `test_agent` with agent\_name='account-data-loader' and this customer data"
4. **MCP Server** invokes the Lambda function and returns the result

**Why this matters:**

- **Standardization**: Any MCP-compatible AI assistant can use your agents (not just Kiro)
- **Discovery**: Tools are discovered dynamically, not hardcoded
- **Testing**: You can test individual agents through natural language without writing test scripts
- **Development speed**: Change your agents, MCP Server automatically exposes the updates

**In this workshop:** You'll use the `test_agent` tool in Chapters 2-5 to test each agent individually. In Chapter 6, you'll see AgentCore Gateway use MCP to expose Lambda agents to production orchestrators.

## Two Deployment Patterns

This workshop demonstrates two architectures for multi-agent systems:

### Development Architecture (Chapters 2-5)

```
Kiro CLI → MCP Server (local) → 5 Lambda Agents → DynamoDB
```

- **MCP Server**: Local Python process for rapid development
- **Lambda Agents**: Stateless, event-driven specialists
- **Use case**: Testing, iteration, and building individual agents

### Production Architecture (Chapter 6)

```
User → AgentCore Runtime (Orchestrator) → AgentCore Gateway → 5 Lambda Agents → DynamoDB
```

- **AgentCore Runtime**: Stateful orchestrator with session management
- **AgentCore Gateway**: Exposes Lambda agents as MCP tools
- **Use case**: Production deployment with streaming, observability, and extended execution

**Chapter 6 Preview:** You'll deploy a production orchestrator on [Amazon Bedrock AgentCore](https://aws.amazon.com/bedrock/agentcore/) that coordinates all 5 Lambda agents through AgentCore Gateway, demonstrating hybrid architecture for production multi-agent systems.

## Pre-Deployed Infrastructure

The following infrastructure is already deployed in your workshop account:

| Service | Resource Name | Purpose |
| --- | --- | --- |
| Lambda — MCP Server | `strands-loan-workshop-mcp-server` | Orchestrates the 5-agent pipeline |
| Lambda — Agent 1 | `strands-loan-workshop-account-data-loader` | Account creation and OTP |
| Lambda — Agent 2 | `strands-loan-workshop-eligibility-filter` | KYC and eligibility |
| Lambda — Agent 3 | `strands-loan-workshop-loan-product-matcher` | Loan creation and repayment |
| Lambda — Agent 4 *(build this)* | `strands-loan-workshop-risk-assessment` | PIN security |
| Lambda — Agent 5 *(build this)* | `strands-loan-workshop-approval-decision` | LLM approval + disbursement |
| DynamoDB Table | `strands-loan-workshop-loan-applications` | Shared state |
| Lambda Layer | `strands-loan-workshop-strands-sdk` | Strands SDK + dependencies |
| AgentCore Gateway *(deploy in Ch 6)* | Created via `setup_gateway.py` | Exposes Lambda agents as MCP tools |
| AgentCore Runtime *(deploy in Ch 6)* | `LoanOrchestrator` | Stateful production orchestrator |

Agents 1–3 have starter code you'll complete in Chapters 2–4. **Agents 4 and 5 you build from scratch in Chapter 5** — solution files are provided in `workshop/solutions/` for reference.

