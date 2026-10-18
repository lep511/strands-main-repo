---
season: 3
season_name: "Season 3 — October 2026 (Autumn / Halloween Edition)"
day: 12
title: "Enforcing Semantic Policy in Plain English"
summary: "Write natural-language governance policies that Agent Gateway evaluates on every tool call to ensure agents only act under approved conditions."
tags: ["Phase 3: Runtime Guardrails", "Governance", "Security"]
canonical_url: "https://adventofagents.com/2026/10/12"
markdown_url: "https://adventofagents.com/2026/10/12.md"
video_url: "https://www.youtube.com/embed/ffCmw69pXvM"
primary_video:
  title: "Day 12: Semantic Governance: Natural-Language Rules"
  creator_name: "Dino Chiesa"
  duration: "13:50"
  video_url: "https://www.youtube.com/embed/ffCmw69pXvM"
---

# ⚖️ Day 12: Enforcing Semantic Policy in Plain English

> **Season 3 — October 2026 (Autumn / Halloween Edition)** · [Interactive Web View](https://adventofagents.com/2026/10/12?utm_source=adventofagents&utm_medium=markdown&utm_campaign=adventofagents_s3_2026&utm_content=day12) · [Raw Markdown](https://adventofagents.com/2026/10/12.md?utm_source=adventofagents&utm_medium=markdown&utm_campaign=adventofagents_s3_2026&utm_content=day12)

**Summary:** Write natural-language governance policies that Agent Gateway evaluates on every tool call to ensure agents only act under approved conditions.

**Day 12 of Google's Advent of Agents — Season 3**

IAM and Agent Gateway authorization policies decide which tools an agent can reach. They cannot express rules that depend on the circumstances of a call: its arguments, what the user asked for, or the conversation so far. Semantic governance policies fill that gap. You write a constraint in plain English, and the policy engine checks every tool call the model proposes against it before the agent can execute it.

![Semantic governance request flow through Agent Gateway](/season3-day12-semantic-governance.png)

**How It Works**

- **Interception at the Gateway**: Agent Gateway inspects each model response. When the model returns a `functionCall`, the Gateway sends it to the policy engine together with the user prompt and chat history.
- **Natural-Language Constraints**: A policy binds a plain-English rule, such as "Deny requests for refunds above $100", to an agent and optionally to specific MCP tools. Tools the policy does not name are unaffected.
- **Verdict Before Execution**: The policy engine returns `ALLOW` or `DENY`. A denied call never reaches the tool, and the agent can return a custom denial message to the user.
- **User Intent Alignment**: The policy engine also checks that a proposed tool call matches what the user actually asked for, which catches instructions injected through untrusted content like emails, web pages, or documents.

**Testing and Auditing**

Every evaluation is written to Cloud Logging with a verdict and a rationale for each tool call. Dry-run mode logs verdicts without blocking, so you can measure a policy's effect on real traffic before enforcing it. Policies bind to an agent identity, so the same tool can be governed for one agent and left open for another.

**Resources:**

- [Configure semantic governance policies](https://g.dev/cloud/adventofagents-season3-docs-configure-semantic-governance)
- [Semantic governance policies overview](https://g.dev/cloud/adventofagents-season3-docs-semantic-governance-policies-overview)
- [Monitor semantic governance](https://g.dev/cloud/adventofagents-season3-docs-monitor-semantic-governance)

## Code & Commands

### Step 1: Check the Policy Engine

```bash
export CLOUDSDK_METRICS_ENVIRONMENT="advent-of-agents-s3-day12"

# Prerequisites: an agent deployed with Agent Identity behind Agent Gateway,
# and the policy engine provisioned (see "Configure semantic governance policies").
export PROJECT_ID="YOUR_PROJECT_ID"
# Any supported location (see "Supported locations" in the setup doc), e.g. us-central1
export LOCATION="YOUR_LOCATION"

# Expect state: ACTIVE
gcloud ai semantic-governance-policy-engine describe \
  --location="$LOCATION" --project="$PROJECT_ID"
```

### Step 2: Look Up the Agent and MCP Server

```bash
export CLOUDSDK_METRICS_ENVIRONMENT="advent-of-agents-s3-day12"

# Uses PROJECT_ID and LOCATION from step 1.
AGENT=$(gcloud agent-registry agents list \
  --location="$LOCATION" --project="$PROJECT_ID" \
  --filter='displayName=YOUR_AGENT_NAME' --format='value(name)')

MCP_SERVER=$(gcloud agent-registry mcp-servers list \
  --location="$LOCATION" --project="$PROJECT_ID" \
  --filter='displayName=YOUR_MCP_SERVER_NAME' --format='value(name)')

echo "$AGENT"; echo "$MCP_SERVER"
```

### Step 3: Create a Semantic Governance Policy

```bash
export CLOUDSDK_METRICS_ENVIRONMENT="advent-of-agents-s3-day12"

# Uses PROJECT_ID and LOCATION from step 1, AGENT and MCP_SERVER from step 2.
gcloud ai semantic-governance-policies create refund-cap-100 \
  --location="$LOCATION" --project="$PROJECT_ID" \
  --display-name="Refund cap \$100" \
  --agent="$AGENT" \
  --mcp-tools="mcp-server=$MCP_SERVER,tools=process_refund" \
  --natural-language-constraint="Deny requests for refunds above \$100."

gcloud ai semantic-governance-policies list \
  --location="$LOCATION" --project="$PROJECT_ID"
```

### Step 4: Read Policy Verdicts from Cloud Logging

```bash
export CLOUDSDK_METRICS_ENVIRONMENT="advent-of-agents-s3-day12"

# Uses PROJECT_ID from step 1.
gcloud logging read \
  'logName="projects/'"$PROJECT_ID"'/logs/semantic-governance-policy"' \
  --project="$PROJECT_ID" --freshness=1h --limit=20 \
  --format='value(timestamp,jsonPayload.verdict)'
```

## Resources & Links

- **[Configure semantic governance policies](https://g.dev/cloud/adventofagents-season3-docs-configure-semantic-governance)** — Provision the policy engine, create policies with the Console or gcloud, enable dry-run mode, and debug enforcement.
- **[Semantic governance policies overview](https://g.dev/cloud/adventofagents-season3-docs-semantic-governance-policies-overview)** — How natural-language constraints and user intent checks are evaluated against proposed tool calls.
- **[Monitor semantic governance](https://g.dev/cloud/adventofagents-season3-docs-monitor-semantic-governance)** — Read policy verdicts and rationales in Cloud Logging and track policy engine activity.
- **[Configure IAM policies for agents](https://g.dev/cloud/adventofagents-season3-docs-configure-iam-policies)** — The deterministic control that decides which tools and services an agent can reach at all.
