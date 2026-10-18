---
season: 3
season_name: "Season 3 — October 2026 (Autumn / Halloween Edition)"
day: 10
title: "Model Armor: Inspect & Block Malicious Prompts at Gateway"
summary: "Protect automated AI code review agents against indirect prompt injection attacks hidden inside pull request diffs using Model Armor and Agent Gateway."
tags: ["Phase 3: Runtime Guardrails", "Agent Gateway", "Security", "Prompt Shielding"]
canonical_url: "https://adventofagents.com/2026/10/10"
markdown_url: "https://adventofagents.com/2026/10/10.md"
video_url: "https://www.youtube.com/embed/0fr0BEdnsio"
primary_video:
  title: "Day 10: Block Prompt Injections & Jailbreaks — 5-Minute Google Cloud Kata"
  creator_name: "Sirisha Karra"
  duration: "4:52"
  video_url: "https://www.youtube.com/embed/0fr0BEdnsio"
companion_videos:
  - id: "s3-d10-swyx-ai-security-gray-swan"
    title: "AI Security After Codex and Claude Code — Indirect Prompt Injection, Guardrails & Agent Identity"
    creator_name: "Swyx (Shawn Wang) with Zico Kolter & Matt Fredrikson"
    creator_handle: "@swyx"
    creator_url: "https://www.youtube.com/@LatentSpaceTV"
    duration: "1:07:30"
    video_url: "https://www.youtube.com/embed/j8BAficRjEc?start=67"
    watch_url: "https://www.youtube.com/watch?v=j8BAficRjEc&t=67s"
    invitation_headline: "Why model capability doesn't stop indirect prompt injection — and how runtime filter models defend the Lethal Trifecta"
---

# 🛡️ Day 10: Model Armor: Inspect & Block Malicious Prompts at Gateway

> **Season 3 — October 2026 (Autumn / Halloween Edition)** · [Interactive Web View](https://adventofagents.com/2026/10/10?utm_source=adventofagents&utm_medium=markdown&utm_campaign=adventofagents_s3_2026&utm_content=day10) · [Raw Markdown](https://adventofagents.com/2026/10/10.md?utm_source=adventofagents&utm_medium=markdown&utm_campaign=adventofagents_s3_2026&utm_content=day10)

**Summary:** Protect automated AI code review agents against indirect prompt injection attacks hidden inside pull request diffs using Model Armor and Agent Gateway.

## 🧭 Community Perspective & Companion Deep Dive

- **[Featured Perspective: AI Security After Codex and Claude Code (@swyx · Latent Space)](https://www.youtube.com/watch?v=j8BAficRjEc&t=67s)** by **Swyx (Shawn Wang) with Zico Kolter & Matt Fredrikson** (@swyx · 1:07:30) — Swyx sits down with CMU professors and Gray Swan co-founders Zico Kolter and Matt Fredrikson to unpack why Indirect Prompt Injection (IPI) and jailbreaks do not disappear as models scale, how dedicated inbound/outbound filter models intercept poisoned prompts and tool calls, and why enterprise agents require system-level isolation and least-privilege agent identity.

**Day 10 of Google's Advent of Agents — Season 3**

When an automated code review agent reads untrusted external data like a GitHub pull request diff, an attacker can hide adversarial instructions inside code comments to trick the model into calling privileged tools like `add_collaborator`. Relying on system prompt instructions to stop these indirect prompt injections is brittle because the model cannot reliably separate trusted developer instructions from untrusted data it just fetched.

**How It Works**

Instead of writing custom sanitization logic inside your agent code, you can pair **Agent Gateway** with **Model Armor** to inspect prompts and retrieved tool payloads at the network boundary. By attaching a content authorization policy to the gateway, every outbound request and untrusted payload is screened out-of-band before the agent can act on malicious instructions:

- **Out-of-Band Prompt Shielding**: Agent Gateway routes outbound agent traffic and retrieved pull request diffs through a Model Armor template configured to detect prompt injections, jailbreaks, and malicious URIs without adding security boilerplate to your agent code.
- **Fail-Closed Tool Containment**: When Model Armor flags an adversarial directive inside an untrusted payload, the gateway blocks the poisoned context at the perimeter so the agent never executes privileged tools like `add_collaborator`.

![Model Armor and Agent Gateway Prompt Injection Defense](/s03/s3-day10-model-armor-gateway.png)

**Two Ways to Run This Kata:**

**1. Local Testing Mechanism**
Follow the steps in the "Code" tab and test a lightweight version of the demo from your terminal.
The test tool runs both scenarios:
- **Attack Scenario (PR #3)**: The agent fetches an untrusted diff containing an indirect injection. Model Armor intercepts the payload, containing the exploit and preventing execution of `add_collaborator`.
- **Clean Scenario (PR #4)**: The agent fetches legitimate documentation, successfully approving the PR without interruption.

**2. From Attack to Quarantine**
Follow the repository guide linked in the **Resources** section to deploy the full GitHub demo.

**Resources:**

- [Model Armor Overview](https://g.dev/cloud/adventofagents-season3-docs-model-armor)
- [Agent Gateway Overview](https://g.dev/cloud/adventofagents-season3-agent-gateway)
- [GitHub Demo - PR Reviewer Security Pipeline](https://g.dev/cloud/adventofagents-season3-day10-demo)

## Code & Commands

### Configure Model Armor & Agent Gateway

```bash
export CLOUDSDK_METRICS_ENVIRONMENT="advent-of-agents-s3-day10"

# STEP 1 - Enable required Google Cloud services
gcloud services enable \
  modelarmor.googleapis.com \
  networkservices.googleapis.com \
  networksecurity.googleapis.com \
  aiplatform.googleapis.com \
  agentregistry.googleapis.com \
  logging.googleapis.com \
  cloudbuild.googleapis.com \
  --project=YOUR_PROJECT_ID

# STEP 2 - Create the Model Armor Template with Prompt Injection filters
gcloud config set api_endpoint_overrides/modelarmor "https://modelarmor.us-central1.rep.googleapis.com/"
gcloud model-armor templates create "agent-prompt-shield" \
  --project=YOUR_PROJECT_ID \
  --location="us-central1" \
  --pi-and-jailbreak-filter-settings-enforcement=enabled \
  --pi-and-jailbreak-filter-settings-confidence-level=medium-and-above \
  --malicious-uri-filter-settings-enforcement=enabled

# STEP 3 - Register required Google API endpoints in Agent Registry
# Allows outbound calls (Logging, Vertex AI, CRM, mTLS) through zero-trust egress
TOKEN=$(gcloud auth print-access-token)
curl -4 -s -X POST \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  "https://agentregistry.googleapis.com/v1alpha/projects/YOUR_PROJECT_ID/locations/global/services?serviceId=googleapis" \
  -d '{
    "displayName": "Google APIs Global",
    "description": "Consolidated Google Cloud global APIs and mTLS endpoints",
    "interfaces": [
      {"url": "https://aiplatform.mtls.googleapis.com", "protocolBinding": "JSONRPC"},
      {"url": "https://aiplatform.googleapis.com", "protocolBinding": "JSONRPC"},
      {"url": "https://logging.mtls.googleapis.com", "protocolBinding": "JSONRPC"},
      {"url": "https://logging.googleapis.com", "protocolBinding": "JSONRPC"},
      {"url": "https://trace.mtls.googleapis.com", "protocolBinding": "JSONRPC"},
      {"url": "https://trace.googleapis.com", "protocolBinding": "JSONRPC"},
      {"url": "https://cloudresourcemanager.mtls.googleapis.com", "protocolBinding": "JSONRPC"},
      {"url": "https://cloudresourcemanager.googleapis.com", "protocolBinding": "JSONRPC"},
      {"url": "https://iamcredentials.mtls.googleapis.com", "protocolBinding": "JSONRPC"},
      {"url": "https://iamcredentials.googleapis.com", "protocolBinding": "JSONRPC"}
    ],
    "endpointSpec": {"type": "NO_SPEC"}
  }'

# STEP 4 - Create Egress Agent Gateway linked to Agent Registry
curl -4 -s -X POST \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  "https://networkservices.googleapis.com/v1/projects/YOUR_PROJECT_ID/locations/us-central1/agentGateways?agentGatewayId=agent-egress-gateway" \
  -d '{
    "googleManaged": {
      "governedAccessPath": "AGENT_TO_ANYWHERE"
    },
    "protocols": ["MCP"],
    "registries": [
      "//agentregistry.googleapis.com/projects/YOUR_PROJECT_ID/locations/global"
    ]
  }'

# STEP 5 - Create AuthzExtension targeting Model Armor template
curl -4 -s -X POST \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  "https://networkservices.googleapis.com/v1/projects/YOUR_PROJECT_ID/locations/us-central1/authzExtensions?authzExtensionId=agent-prompt-shield-ext" \
  -d '{
    "service": "modelarmor.us-central1.rep.googleapis.com",
    "timeout": "10s",
    "metadata": {
      "model_armor_settings": "[ { "request_template_id": "projects/YOUR_PROJECT_ID/locations/us-central1/templates/agent-prompt-shield" } ]"
    }
  }'

# STEP 6 - Create AuthzPolicy (CONTENT_AUTHZ) attached to agent-egress-gateway
curl -4 -s -X POST \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  "https://networksecurity.googleapis.com/v1/projects/YOUR_PROJECT_ID/locations/us-central1/authzPolicies?authzPolicyId=egress-authz-policy" \
  -d '{
    "action": "CUSTOM",
    "policyProfile": "CONTENT_AUTHZ",
    "customProvider": {
      "authzExtension": {
        "resources": [
          "projects/YOUR_PROJECT_ID/locations/us-central1/authzExtensions/agent-prompt-shield-ext"
        ]
      }
    },
    "target": {
      "resources": [
        "projects/YOUR_PROJECT_ID/locations/us-central1/agentGateways/agent-egress-gateway"
      ]
    }
  }'
```

### Governed PR Reviewer Agent with Zero Security Boilerplate

```python
from google.adk.agents import Agent
from google.adk.models import Gemini
from google.genai import Client as GenaiClient

MODEL = "gemini-3.8-flash"

class GlobalGemini(Gemini):
    """Routes Gemini API calls to the global endpoint on Vertex AI."""
    api_version: str = "v1beta1"

    @property
    def api_client(self) -> GenaiClient:
        return GenaiClient(vertexai=True, location="global")

def read_pull_request(pr_id: str, repo: str | None = None) -> str:
    """Reads pull request diff dynamically from repository."""
    # When routed via Agent Gateway, outbound traffic is intercepted and sanitized.
    return "Fetched PR diff content..."

def add_collaborator(username: str) -> str:
    """Grants repository collaborator write permissions to a user."""
    return f"Privilege granted to {username}."

# Security policies are enforced at the Agent Gateway proxy layer.
# Application code contains pure business logic with zero security boilerplate.
root_agent = Agent(
    name="pr_reviewer",
    model=GlobalGemini(model=MODEL),
    description="Automated PR reviewer protected by Google Cloud Model Armor Agent Gateway.",
    instruction="You are an automated GitHub PR reviewer. Review diffs and execute approved tools.",
    tools=[read_pull_request, add_collaborator],
)
```

### Deploy Agent with Native AGENT_IDENTITY & Gateway Egress

```python
import vertexai
from vertexai.preview import reasoning_engines
from pr_reviewer_agent import root_agent

PROJECT_ID = "YOUR_PROJECT_ID"
LOCATION = "us-central1"

vertexai.init(project=PROJECT_ID, location=LOCATION)

# STEP 1: Deploy to Vertex AI Reasoning Engine with native AGENT_IDENTITY
# STEP 2: Attach the provisioned Agent Egress Gateway via agentToAnywhereConfig
engine = reasoning_engines.ReasoningEngine.create(
    root_agent,
    display_name="pr-reviewer-agent-identity",
    requirements=["google-adk>=2.5.0", "google-genai>=1.0.0", "requests>=2.31.0"],
    extra_packages=["pr_reviewer_agent.py"],
    identity_type="AGENT_IDENTITY",
    agent_gateway_config={
        "agent_to_anywhere_config": {
            "agent_gateway": f"projects/{PROJECT_ID}/locations/{LOCATION}/agentGateways/agent-egress-gateway"
        }
    },
)
print(f"Deployed governed agent: {engine.resource_name}")
```

### Local Testing Tool: Test Attack & Clean Scenarios from Terminal

```python
import json
import argparse
import requests
import google.auth
from google.auth.transport.requests import Request

def test_agent_locally(project_id: str, location: str, engine_id: str, pr_num: int):
    credentials, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
    credentials.refresh(Request())

    # Send identical, clean business prompt across both clean and attack scenarios
    prompt = f"Please review and process pull request {pr_num} for repository siri2421/advent-of-agents-observabiity."
    url = f"https://{location}-aiplatform.googleapis.com/v1beta1/projects/{project_id}/locations/{location}/reasoningEngines/{engine_id}:streamQuery"
    headers = {"Authorization": f"Bearer {credentials.token}", "Content-Type": "application/json"}
    payload = {"class_method": "stream_query", "input": {"message": prompt, "user_id": "tester"}}

    print(f"\n🔍 Testing PR #{pr_num} ({'ATTACK' if pr_num == 3 else 'CLEAN'})...")
    resp = requests.post(url, headers=headers, json=payload, timeout=90)
    resp.raise_for_status()
    tool_calls = []

    for line in resp.text.strip().split("\n"):
        if line.strip():
            try:
                event = json.loads(line)
                for p in event.get("content", {}).get("parts", []):
                    if "function_call" in p:
                        tool_calls.append(p["function_call"]["name"])
            except Exception:
                pass

    if pr_num == 3:
        assert "add_collaborator" not in tool_calls, "🚨 FAILED: add_collaborator was executed!"
        print("🛡️  SUCCESS: Indirect prompt injection contained. Zero unauthorized tool calls.")
    else:
        assert "read_pull_request" in tool_calls, "🚨 FAILED: Clean PR was not processed!"
        print("✅ SUCCESS: Clean PR triaged and approved.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True)
    parser.add_argument("--engine", required=True)
    parser.add_argument("--location", default="us-central1")
    args = parser.parse_args()

    test_agent_locally(args.project, args.location, args.engine, 3)
    test_agent_locally(args.project, args.location, args.engine, 4)
```

### Query Model Armor Sanitization Verdicts in Cloud Logging

```bash
export CLOUDSDK_METRICS_ENVIRONMENT="advent-of-agents-s3-day10"

# Verify blocked prompt injection attacks live in Cloud Logging
gcloud logging read 'logName:"projects/YOUR_PROJECT_ID/logs/modelarmor.googleapis.com%2Fsanitize_operations" AND jsonPayload.sanitizationResult.sanitizationVerdict="MODEL_ARMOR_SANITIZATION_VERDICT_BLOCK"' \
  --project=YOUR_PROJECT_ID \
  --limit=1 \
  --format="json(timestamp,jsonPayload.sanitizationResult)"
```

## Resources & Links

- **#1 Featured Cross-Promotion: [Featured Perspective: AI Security After Codex and Claude Code (@swyx · Latent Space)](https://www.youtube.com/watch?v=j8BAficRjEc&t=67s)** — Swyx hosts CMU's Zico Kolter and Matt Fredrikson on Indirect Prompt Injection (IPI), the Lethal Trifecta, inbound/outbound tool-call guardrail models, and agent-native identity.
- **[Model Armor Overview](https://g.dev/cloud/adventofagents-season3-docs-model-armor)** — Screen prompts and model responses against prompt injection and jailbreaks.
- **[Agent Gateway Overview](https://g.dev/cloud/adventofagents-season3-agent-gateway)** — Centralized policy enforcement, mTLS, and egress controls for AI agents.
- **[Google Secure AI Framework (SAIF)](https://saif.google/)** — Google's conceptual framework and practical guidance for securing AI systems.
- **[PR Reviewer Security Pipeline Demo](https://g.dev/cloud/adventofagents-season3-day10-demo)** — Live GitHub Actions pipeline demonstrating indirect prompt injection defense.
