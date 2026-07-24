# Knowledge Base Agent

An interactive CLI agent that answers user questions using documents stored in an Amazon Bedrock Managed Knowledge Base. Built with [Strands Agents](https://github.com/strands-agents/strands-agents) and powered by semantic search.

## How It Works

1. The user asks a question in natural language.
2. The agent performs semantic search against the Bedrock Knowledge Base using the `managedSearchConfiguration` API.
3. Retrieved document chunks are filtered by relevance score.
4. A Strands Agent (backed by an LLM) generates a grounded answer using **only** the retrieved context — it never invents information.

## Features

- **Grounded answers** — the agent strictly answers from retrieved documents and explicitly states when information is insufficient.
- **Relevance scoring** — results below a configurable minimum score threshold are discarded.
- **Context transparency** — the retrieved context is displayed before the agent's answer.
- **Multi-language** — answers in the same language as the user's question.

## Prerequisites

- Python 3.13+
- [uv](https://docs.astral.sh/uv/) package manager
- AWS credentials configured with permissions for:
  - `bedrock-agent-runtime:Retrieve`
  - `bedrock-agent:ListDataSources`
  - `bedrock-agent:GetKnowledgeBase`
- An active Amazon Bedrock Managed Knowledge Base with indexed documents

## Installation

```bash
uv sync
```

## Configuration

Set the following environment variables:

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `STRANDS_KNOWLEDGE_BASE_ID` | Yes | — | The ID of your Bedrock Knowledge Base (alphanumeric only) |
| `AWS_REGION` | No | `us-east-1` | AWS region where the Knowledge Base is deployed |

### Example

```bash
export STRANDS_KNOWLEDGE_BASE_ID="PHXTT2FZSH"
export AWS_REGION="us-east-1"
```

## Usage

```bash
uv run main.py
```

### Interactive Session

```
🧠 Knowledge Base Agent 🧠

This agent helps you retrieve information from your knowledge base.
Type your request below or 'exit' to quit:

> What are LLMs?
Processing...

--- Context retrieved from knowledge base ---
Result 1 (score: 0.4609):
...document content...
--- End of context ---

LLMs (Large Language Models) are AI systems trained on massive text corpora...

> exit

Goodbye! 👋
```

## Project Structure

```
knowledge-base-agent/
├── main.py          # Application entry point and agent logic
├── pyproject.toml   # Project dependencies and metadata
├── uv.lock          # Locked dependency versions
└── README.md
```

## Dependencies

- **strands-agents** — Agent framework for orchestrating LLM interactions
- **strands-agents-tools** — Tool library for Strands agents
- **boto3** — AWS SDK for calling Bedrock Knowledge Base APIs

## Architecture

```
User Query
    │
    ▼
┌─────────────────────────────┐
│  Bedrock Knowledge Base     │
│  (managedSearchConfig)      │
└─────────────┬───────────────┘
              │ Retrieved chunks
              ▼
┌─────────────────────────────┐
│  Strands Agent (LLM)        │
│  - Grounded answers only    │
│  - No tools (no recursion)  │
│  - Same language as query   │
└─────────────┬───────────────┘
              │
              ▼
         Answer to user
```
