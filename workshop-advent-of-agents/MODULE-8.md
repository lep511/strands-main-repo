---
season: 3
season_name: "Season 3 — October 2026 (Autumn / Halloween Edition)"
day: 8
title: "Agent Policies: Stop Agents from Calling Dangerous Tools"
summary: "Enforce network-level IAM access policies and tool deny rules through Agent Gateway to block destructive agent actions."
tags: ["Phase 2: IAM", "Agent Identity", "IAM", "Security"]
canonical_url: "https://adventofagents.com/2026/10/08"
markdown_url: "https://adventofagents.com/2026/10/08.md"
video_url: "https://www.youtube.com/embed/l6I5POMbqME"
primary_video:
  title: "Day 8: Least-Privilege IAM Policies for Tools — 5-Minute Google Cloud Kata"
  creator_name: "James Meyer"
  duration: "5:24"
  video_url: "https://www.youtube.com/embed/l6I5POMbqME"
companion_videos:
  - id: "s3-d08-abhishek-veeramalla-gateway-iam"
    title: "Google Cloud AI Agent Zero to Hero Series (Sep/Oct 2026): Build, Deploy, Govern & Observe"
    creator_name: "Abhishek Veeramalla"
    creator_handle: "@AbhishekVeeramalla"
    creator_url: "https://www.youtube.com/@AbhishekVeeramalla"
    duration: "12:26"
    video_url: "https://www.youtube.com/embed/QE-jDKvh4yU"
    watch_url: "https://www.youtube.com/watch?v=QE-jDKvh4yU"
    invitation_headline: "Follow Abhishek Veeramalla's live 2026 Google Cloud 'AI Agent Zero to Hero' series"
---

# 🛡️ Day 8: Agent Policies: Stop Agents from Calling Dangerous Tools

> **Season 3 — October 2026 (Autumn / Halloween Edition)** · [Interactive Web View](https://adventofagents.com/2026/10/08?utm_source=adventofagents&utm_medium=markdown&utm_campaign=adventofagents_s3_2026&utm_content=day08) · [Raw Markdown](https://adventofagents.com/2026/10/08.md?utm_source=adventofagents&utm_medium=markdown&utm_campaign=adventofagents_s3_2026&utm_content=day08)

**Summary:** Enforce network-level IAM access policies and tool deny rules through Agent Gateway to block destructive agent actions.

## 🧭 Community Perspective & Companion Deep Dive

- **[Featured Series: AI Agent Zero to Hero on Google Cloud (@AbhishekVeeramalla · Sep/Oct 2026)](https://www.youtube.com/watch?v=QE-jDKvh4yU)** by **Abhishek Veeramalla** (@AbhishekVeeramalla · 12:26) — Pair today's Agent Gateway & IAM Unified Access Policy (UAP) kata with Abhishek Veeramalla's active September/October 2026 Google Cloud series (`1. Build, 2. Deploy & Scale, 3. Govern with SPIFFE & Agent Gateway, 4. Observe`).

**Day 8 of Google's Advent of Agents — Season 3**

When you connect an AI agent to an MCP server or external API, that server often bundles safe read-only tools (`lookup_order`) alongside high-risk tools (`issue_refund`, `delete_account`) on the same endpoint. Telling an agent "never delete customer accounts" in its system prompt is not a security boundary, because a prompt injection or model mistake can still trigger the tool.

**Agent Gateway** acts as a network security checkpoint between your agents (whether running on Agent Runtime, Cloud Run, Gemini Enterprise, or external platforms) and the tools they call, inspecting every outbound request and enforcing **IAM Unified Access Policies** before traffic ever reaches your backend.

![Agent Gateway Least-Privilege Tool Governance](/s03/s3-day08-agent-gateway.png)

Because Agent Gateway blocks all outbound traffic by default, you govern what an agent can call using a single IAM Access policy that pairs an `ALLOW` rule with a `DENY` rule, bound to the agent's cryptographic identity from Day 5.

* The `ALLOW` rule opens access to trusted destinations, including Google Cloud APIs (`googleapis.com` for Gemini and logging) and approved MCP servers cataloged in **Agent Registry**.
* The `DENY` rule acts as a hard guardrail: because `DENY` rules are always evaluated first, a simple condition checking `destination.agent_registry.mcp_server.tool.name` immediately blocks `delete_account` and `issue_refund` at the proxy with `HTTP 403 Forbidden`, while safe calls like `lookup_order` pass right through.

**Resources:**

- [Agent Gateway Overview](https://g.dev/cloud/adventofagents-season3-agent-gateway)
- [IAM Access Policies Overview](https://g.dev/cloud/adventofagents-season3-day8-iam-access-policies)
- [CEL Attributes for IAM Access Policies](https://g.dev/cloud/adventofagents-season3-docs-policies-cel-attributes)
- [Reference Implementation Repository](https://g.dev/cloud/adventofagents-season3-day8-github-demo)

## Code & Commands

### Turnkey Deployment & Verification

```bash
# 1. Clone the reference demo repository
git clone https://github.com/jamesmeyergithub/agent-gateway.git
cd agent-gateway

# 2. Deploy infrastructure & agent in a single command:
#    - Creates regional Agent Gateway with VPC network egress
#    - Configures TLS trust via Agent Gateway Root CA certificate
#    - Registers tools in Agent Registry (lookup_order, issue_refund, delete_account)
#    - Deploys IAM Unified Access Policy with tool-level CEL DENY rules
#    - Deploys ADK Reasoning Engine with native cryptographic SPIFFE Agent Identity
./scripts/deploy_gcp.sh --project YOUR_PROJECT_ID --region YOUR_REGION

# 3. Run automated live boundary verification:
./scripts/deploy_gcp.sh --project YOUR_PROJECT_ID --region YOUR_REGION --verify-only

# 4. Clean up all regional resources safely when finished:
./scripts/cleanup.sh --project YOUR_PROJECT_ID --region YOUR_REGION --yes
```

### IAM Access Policy (Tool DENY Rules)

```json
{
  "rules": [
    {
      "description": "Deny destructive and financial actions at the network boundary",
      "effect": "DENY",
      "principals": [
        "principalSet://agents.global.org-YOUR_ORG_ID.system.id.goog/*"
      ],
      "conditions": {
        "iap.googleapis.com": {
          "expression": "destination.agent_registry.mcp_server.tool.name == 'delete_account' || destination.agent_registry.mcp_server.tool.name == 'issue_refund'"
        }
      },
      "operation": {
        "permissions": ["iap.googleapis.com/resources.egressViaIAP"]
      }
    },
    {
      "description": "Allow all agent egress to googleapis and registered resources",
      "effect": "ALLOW",
      "principals": [
        "principalSet://agents.global.org-YOUR_ORG_ID.system.id.goog/*"
      ],
      "conditions": {
        "iap.googleapis.com": {
          "expression": "destination.unregistered.host.endsWith('googleapis.com') || destination.is_registered == true"
        }
      },
      "operation": {
        "permissions": ["iap.googleapis.com/resources.egressViaIAP"]
      }
    }
  ]
}
```

### Governed Agent & Tools

```python
# Sample code — see deploy_gcp.sh in the Github Repo to deploy the end to end demo.
import os
import certifi
import httpx
from google.adk.agents import Agent
from google.adk.apps import App
from google.adk.models import Gemini
from google.genai import types

# 1. Configure Agent Gateway CA certificate bundle for mTLS egress
ca_cert = os.path.join(os.path.dirname(__file__), "agent_gateway_ca.crt")
if os.path.exists(ca_cert):
    combined_ca = "/tmp/combined_agent_gateway_ca.crt"
    with open(combined_ca, "w") as out_f, open(certifi.where()) as in_f, open(ca_cert) as ca_f:
        out_f.write(in_f.read() + "\n" + ca_f.read())
    os.environ["SSL_CERT_FILE"] = combined_ca

MODEL = "gemini-3.1-pro"
GATEWAY_MCP_URL = "https://backend-tools.us-west1.run.app/mcp"

# READ TOOL: Allowed by IAM policy (HTTP 200 OK)
def lookup_order(order_id: str) -> dict:
    """Check order status and tracking details."""
    payload = {"jsonrpc": "2.0", "method": "tools/call", "params": {"name": "lookup_order", "arguments": {"order_id": order_id}}}
    resp = httpx.post(GATEWAY_MCP_URL, json=payload, timeout=5.0)
    return resp.json()

# RESTRICTED FINANCIAL TOOL: Denied by Agent Gateway IAM Policy (HTTP 403 Forbidden)
def issue_refund(order_id: str, amount: float, reason: str = "Customer Request") -> dict:
    """CRITICAL: Process a monetary refund through protected MCP server."""
    payload = {"jsonrpc": "2.0", "method": "tools/call", "params": {"name": "issue_refund", "arguments": {"order_id": order_id, "amount": amount}}}
    resp = httpx.post(GATEWAY_MCP_URL, json=payload, timeout=5.0)
    if resp.status_code == 403:
        return {"status": "BLOCKED_BY_AGENT_GATEWAY", "error": "HTTP 403 Forbidden: Blocked by Agent Gateway IAM Policy"}
    return resp.json()

# RESTRICTED DESTRUCTIVE TOOL: Denied by Agent Gateway IAM Policy (HTTP 403 Forbidden)
def delete_account(customer_id: str) -> dict:
    """CRITICAL: Permanently delete customer record through protected MCP server."""
    payload = {"jsonrpc": "2.0", "method": "tools/call", "params": {"name": "delete_account", "arguments": {"customer_id": customer_id}}}
    resp = httpx.post(GATEWAY_MCP_URL, json=payload, timeout=5.0)
    if resp.status_code == 403:
        return {"status": "BLOCKED_BY_AGENT_GATEWAY", "error": "HTTP 403 Forbidden: Blocked by Agent Gateway IAM Policy"}
    return resp.json()

root_agent = Agent(
    name="customer_support_agent",
    model=Gemini(model=MODEL, retry_options=types.HttpRetryOptions(attempts=3)),
    instruction="You are a customer service support agent. Help customers verify order statuses.",
    tools=[lookup_order, issue_refund, delete_account],
)

app = App(root_agent=root_agent, name="agent-gateway-iam-demo")
```

## Resources & Links

- **#1 Featured Cross-Promotion: [Featured Series: AI Agent Zero to Hero on Google Cloud (@AbhishekVeeramalla · Sep/Oct 2026)](https://www.youtube.com/watch?v=QE-jDKvh4yU)** — Abhishek Veeramalla's live September/October 2026 Google Cloud series covering ADK, Agent Engine, SPIFFE Identity, Agent Gateway, and Model Armor (83K+ views in 3 days).
- **[Github Demo Repository](https://g.dev/cloud/adventofagents-season3-day8-github-demo)** — Provides a repository of deployable code to test the solution in your own environment, and provides additional insights into how it works.
- **[CEL attributes for IAM Access policies](https://g.dev/cloud/adventofagents-season3-docs-policies-cel-attributes)** — Common Expression Language (CEL) attributes and functions that you can use when writing conditional expressions in IAM Unified Access Policies (Access policies) for Agent Gateway.
- **[IAM Access Policies Overview](https://g.dev/cloud/adventofagents-season3-day8-iam-access-policies)** — Understand the ingress and egress policy enforcement chains, IAP checks, and CEL evaluation.
- **[Agent Development Kit (ADK) Documentation](https://google.github.io/adk-docs/?utm_source=adventofagents&utm_medium=markdown&utm_campaign=adventofagents_s3_2026&utm_content=day08)** — Build production agents with secure Model Context Protocol (MCP) tool integrations.
