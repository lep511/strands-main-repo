# Bedrock Guardrails Lab

ITSM (IT Service Management) agent with Amazon Bedrock Knowledge Bases and Guardrails. Demonstrates how to build a RAG-powered agent and progressively add content filtering, PII masking, word filters, and topic denial.

## Prerequisites

- AWS account with Bedrock model access enabled
- Python 3.13 (managed via `uv`)
- AWS CLI v2 configured with valid credentials

## Quick Start

### 1. Create the Knowledge Base

```bash
bash create_knowledge_base.sh
```

Creates an S3 bucket (`kb-demokb123-<account-id>`), an S3 Vectors index, IAM role, Bedrock Knowledge Base, and S3 data source. The script is idempotent.

### 2. Upload documents and ingest

```bash
aws s3 cp Fictitious-Company-Employee-IT-Handbook.pdf s3://kb-demokb123-<account-id>/
aws s3 cp trade_secrets.txt s3://kb-demokb123-<account-id>/
aws s3 cp employee_data.csv s3://kb-demokb123-<account-id>/
aws bedrock-agent start-ingestion-job --knowledge-base-id <kb-id> --data-source-id <ds-id>
```

### 3. Run the CLI agent

```bash
export STRANDS_KNOWLEDGE_BASE_ID=<kb-id>
python knowledge_base_agent.py
```

On startup, choose whether to enable guardrails. If the guardrail hasn't been created yet, the agent will suggest running the notebook first.

### 4. Run the Guardrails notebook

Open `cc_bedrock_guardrails_lab.ipynb` with the **Python 3.13** kernel and follow the steps:

- **Step 3** -- Test the agent without guardrails
- **Step 4** -- Create a guardrail with content filters (violence, hate, prompt attacks) and PII masking
- **Step 5** -- Add word filters (confidential, proprietary)
- **Step 6** -- Add topic denial (trade secrets, competitor info, employee data extraction)

## Key Components

- **`create_knowledge_base.sh`** -- Bash script that provisions all KB infrastructure using S3 Vectors (no OpenSearch Serverless needed).
- **`knowledge_base_agent.py`** -- CLI agent that retrieves from the KB via `bedrock-agent-runtime`, generates answers via the Converse API, and optionally screens input/output with `ApplyGuardrail`.
- **`cc_bedrock_guardrails_lab.ipynb`** -- Step-by-step notebook to create and test Bedrock Guardrails with an AgentCore Harness.

## Sample Documents

| File | Contents |
|------|----------|
| `Fictitious-Company-Employee-IT-Handbook.pdf` | IT policies (passwords, BYOD, remote work, security) |
| `employee_data.csv` | Employee records with PII (names, emails, phones, SSNs) |
| `trade_secrets.txt` | Proprietary company information |

## Architecture

1. **Knowledge Base** -- Bedrock KB with S3 Vectors store and Titan Embed V2 embeddings
2. **Agent** -- Claude Sonnet 4.5 via the Converse API for answer generation
3. **Guardrails** -- Applied via the `ApplyGuardrail` standalone API (pre-screens input, post-screens output)
4. **AgentCore Harness** -- Managed agent loop used by the notebook (`itsm_guardrails_agent`)
