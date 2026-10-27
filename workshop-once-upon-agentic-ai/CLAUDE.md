# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

A workshop that teaches the [Strands Agents SDK](https://strandsagents.com/) by building a Game Master for a fantasy RPG. Each numbered folder is one chapter; chapters build on each other sequentially. Files contain `# TODO` markers for participants to fill in. Solution branches are named `solution-*`.

The agents run on **Amazon Bedrock** (Claude Sonnet 4.6 by default). Chapter 8 deploys everything to **Bedrock AgentCore**.

## Build and Run

```bash
uv sync                    # install all deps into .venv/
source .venv/bin/activate
```

No lockfile is checked in (`uv.lock` is gitignored); `uv sync` resolves fresh each time.

### Running chapters

Each chapter is a standalone script or server. Run from the repo root:

```bash
# Ch 1-3: single-file agents
uv run python 1_strands_basics/simple_agent.py
uv run python 3_custom_tools/agent_with_dice_roll_tool.py

# Ch 4: MCP dice server (port 8002), then the client
uv run python 4_mcp_integration/dice_roll_mcp_server.py
uv run python 4_mcp_integration/gamemaster_mcp_client.py

# Ch 5: start three processes (each in its own terminal)
python 5_a2a_integration/utils/create_knowledge_base.py   # once, needs DnD_BasicRules_2018.pdf
uv run python 5_a2a_integration/agents/rules_agent/rules_agent.py          # port 8000
uv run python 5_a2a_integration/agents/character_agent/character_agent.py   # port 8001
uv run python 5_a2a_integration/agents/gamemaster_orchestrator/gamemaster_orchestrator.py  # port 8009

# Ch 7: same three servers from Ch 5 must be running, then:
uv run python 7_strands_harness/gamemaster_harness.py      # port 8009

# Ch 8: each subfolder has its own pyproject.toml and deploys to AgentCore
```

### Tests

```bash
uv run pytest tests/
```

Tests cover Chapter 5 A2A servers: module imports, per-context `agent_factory` isolation, and the agent card served over HTTP.

## Architecture

### Dependency constraints

- `mcp<2` - Chapter 4 uses `FastMCP` which was renamed in mcp 2.0. Do not bump without porting chapter 4.
- `strands-agents[a2a]>=1.61` - `make_a2a_client` list-of-endpoints form requires >=1.57.2.
- `strands-harness>=0.3` - Chapter 7's `create_harness`.

<!-- BEGIN AWS Agent Toolkit rules -->
## AWS Guidance

- Where these AWS rules conflict with the project's own instructions, the
  project's instructions take precedence.
- Prefer the AWS MCP Server for AWS interactions - it provides sandboxed
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
<!-- END AWS Agent Toolkit rules -->
