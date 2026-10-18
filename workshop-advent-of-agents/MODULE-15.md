---
season: 3
season_name: "Season 3 — October 2026 (Autumn / Halloween Edition)"
day: 15
title: "Agent Memory: Stop Leaks Across Users, Teams & Regions"
summary: "Stop agent memory from leaking between customers, departments, and regions with Memory Bank scopes and Cloud IAM Conditions."
tags: ["Phase 3: Data Protection", "IAM Conditions", "GDPR", "Governance"]
canonical_url: "https://adventofagents.com/2026/10/15"
markdown_url: "https://adventofagents.com/2026/10/15.md"
video_url: "https://www.youtube.com/embed/ZVGaoOG0y3Y"
primary_video:
  title: "Day 15: Memory Isolation & Regional Compliance (GDPR)"
  creator_name: "Joyce Chen"
  duration: "14:48"
  video_url: "https://www.youtube.com/embed/ZVGaoOG0y3Y"
---

# 🔐 Day 15: Agent Memory: Stop Leaks Across Users, Teams & Regions

> **Season 3 — October 2026 (Autumn / Halloween Edition)** · [Interactive Web View](https://adventofagents.com/2026/10/15?utm_source=adventofagents&utm_medium=markdown&utm_campaign=adventofagents_s3_2026&utm_content=day15) · [Raw Markdown](https://adventofagents.com/2026/10/15.md?utm_source=adventofagents&utm_medium=markdown&utm_campaign=adventofagents_s3_2026&utm_content=day15)

**Summary:** Stop agent memory from leaking between customers, departments, and regions with Memory Bank scopes and Cloud IAM Conditions.

**Day 15 of Google's Advent of Agents — Season 3**

When an enterprise banking agent remembers customer preferences across sessions, storing every user's facts in one shared pool creates immediate privacy and compliance risks. A prompt-injected model could ask a custom tool for another customer's account details, a Wealth Management agent could pass Retail Banking scope labels in code to read or poison those memories, or a US agent could query European customer data in violation of GDPR. System prompt instructions cannot prevent this, because the model itself cannot enforce tenant or regional boundaries.

Unlike single-turn chat history that disappears when a conversation ends, **Gemini Enterprise Agent Platform Memory Bank** extracts and stores durable facts about a user across sessions. Each memory is tagged with a scope of up to five key-value labels, such as a user ID and department name, and retrieval requires a 100% exact match on every label, with no wildcards. ADK's built-in memory service attaches the user ID and app name automatically, but scope matching alone cannot stop the three failures above.

**How It Works**

**Memory Bank** solves this with defense-in-depth isolation that works across any agent framework or runtime, including ADK. Instead of trusting the model to filter its own queries, you layer three progressive steps:
- **Exact-match scopes** set from server-side session context
- **Cloud IAM Conditions** bound to the agent identities introduced in Day 5, and
- **Regional Memory Bank instances**.

Every memory operation is validated from your application server down to Google Cloud infrastructure, and you can configure the policies in the Google Cloud console, the gcloud CLI, or Terraform.

![Gemini Enterprise Agent Platform Memory Bank: 3-Step Isolation](/s03/s3-day15-memory-isolation.png)

- **Step 1: Isolate Users with Server-Side Session Context**: Your backend builds the scope from the authenticated user ID and department in server-side session context (`ToolContext` in ADK, hidden from the model), so the LLM cannot pass a user ID as a tool argument. Memory Bank's exact match then returns Alice's memories to Alice and none of them to Charlie.
- **Step 2: Isolate Departments with a Cloud IAM Condition**: Each department's agent runs under its own identity (a dedicated service account or the SPIFFE identity from Day 5) with a Cloud IAM Condition on its Memory Bank role binding. The Wealth Management agent is only allowed the Wealth Management scope label, so its request for `retail_banking` is blocked with `403 Permission Denied` before Memory Bank runs.
- **Step 3: Isolate Regions for GDPR with Separate Memory Banks**: Project-level IAM roles apply in every region, and a US Retail agent already passes the Retail Banking check. You therefore provision separate Memory Bank instances in the US and Europe and add a resource path check to each identity's IAM Condition. The US agent is only allowed on Memory Banks whose resource name starts with the US location, so its cross-border call to the European instance is blocked with `403 Permission Denied`.

**Resources:**

- [Day 15 Kata Demo Repository](https://g.dev/cloud/adventofagents-season3-day15-demo)
- [Agent Platform Memory Bank Overview](https://g.dev/cloud/adventofagents-season3-docs-memory-bank-overview)
- [Memory Bank IAM Conditions](https://g.dev/cloud/adventofagents-season3-docs-memory-bank-iam-conditions)
- [Fetch Memories & Exact-Match Scopes](https://g.dev/cloud/adventofagents-season3-docs-memory-bank-fetch-memories)

## Code & Commands

### 1. Start Here: Run the 3-Step Verification Demo (quickstart.sh)

```bash
export CLOUDSDK_METRICS_ENVIRONMENT="advent-of-agents-s3-day15"

# START HERE: run these commands in Cloud Shell or your terminal to deploy the US & EU Memory Banks
# and test all 3 steps live. Snippets 2 and 3 are for reference only; the repo already contains them.
#
# Prerequisites: Terraform, gcloud with Application Default Credentials
# (gcloud auth application-default login), and Python with google-adk and
# google-cloud-aiplatform installed (pip install -r agent/requirements.txt).
# If $GOOGLE_CLOUD_PROJECT is empty, deploy.sh uses your active gcloud project.

# 1. Clone the Day 15 reference demo and enter the directory:
git clone https://github.com/chjoyce/advent-of-agents-day15
cd advent-of-agents-day15

# 2. Provision US & EU Memory Banks and Conditional IAM policies with Terraform:
chmod +x deploy.sh
./deploy.sh $GOOGLE_CLOUD_PROJECT

# 3. Run the 3-step live verification demo:
python3 demo.py --act 1   # Step 1 (User Scope): Alice recalls her own facts; Charlie gets 0 of Alice's memories
python3 demo.py --act 2   # Step 2 (Department IAM): Wealth Agent -> Retail scope blocked with 403 PERMISSION_DENIED
python3 demo.py --act 3   # Step 3 (GDPR Region IAM): US Agent -> EU Memory Bank blocked with 403 PERMISSION_DENIED
```

### 2. Reference: Step 1 User Isolation in ADK (agent/agent.py)

```python
# REFERENCE ONLY: simplified excerpt of agent/agent.py from the Day 15 demo repo.
# You do not need to copy it. The repo cloned in snippet 1 (quickstart.sh) already contains it.
#
# What Memory Bank does built-in vs. what you write in Step 1:
#   - Built-in: RetrieveMemories(scope=...) checks for a 100% exact dictionary match on scope (no wildcards).
#   - Built-in ADK vs. Custom Tool: ADK's built-in VertexAiMemoryBankService sends scope={"user_id", "app_name"}
#     automatically, but when you write a custom tool to add department keys (like "lob") or regional routing,
#     you must read user_id and tenant_lob from server-side ToolContext so the LLM cannot spoof them.

from google.adk.tools import ToolContext
import vertexai  # Agent Platform Memory Bank SDK client

# 1. What you do: Build the scope dictionary from server-side ToolContext (hidden from LLM tool arguments)
def _resolve_memory_context(tool_context: ToolContext) -> tuple[str, str, dict[str, str]]:
    verified_user_id = tool_context.user_id
    verified_lob = tool_context.state.get("tenant_lob")
    verified_region = tool_context.state.get("data_region", "us-central1")

    if not verified_user_id or not verified_lob:
        raise PermissionError("Missing verified user_id or tenant_lob in server session context.")

    memory_bank_name = REGIONAL_MEMORY_BANKS.get(verified_region)
    if not memory_bank_name:
        raise ValueError(f"No regional Memory Bank configured for data_region={verified_region!r}")

    # What gets checked:
    # - Memory Bank checks 100% exact match on this scope dict (Step 1: isolates Alice from Charlie)
    # - Cloud IAM Condition checks scope["lob"] before Memory Bank runs (Step 2: isolates Retail from Wealth)
    scope = {
        "lob": str(verified_lob),
        "user_id": str(verified_user_id),
    }
    return verified_region, memory_bank_name, scope

# 2. Call RetrieveMemories with the server-verified scope
def recall_memories(query: str, tool_context: ToolContext) -> dict:
    """Searches long-term memories for the current authenticated user."""
    region, memory_bank_name, scope = _resolve_memory_context(tool_context)
    client = vertexai.Client(project=PROJECT_ID, location=region)
    retrieved = client.agent_engines.memories.retrieve(
        name=memory_bank_name,
        scope=scope,
        similarity_search_params={"search_query": query, "top_k": 5},
    )
    return {"region": region, "scope": scope, "memories": [m.memory.fact for m in retrieved]}
```

### 3. Reference: Steps 2 & 3 Department & Regional IAM (terraform/main.tf)

```hcl
# REFERENCE ONLY: simplified excerpt of terraform/main.tf from the Day 15 demo repo.
# You do not need to copy it. ./deploy.sh in snippet 1 (quickstart.sh) applies it for you.
#
# What you configure in Terraform for Steps 2 & 3:
#   - Step 2 (Department Isolation): Without IAM conditions, any agent with roles/aiplatform.memoryUser
#     can pass scope={"lob": "retail_banking"} in code. Adding an IAM Condition on memoryScope['lob']
#     makes Cloud IAM block a Wealth Agent from reading or writing Retail scopes with 403 PERMISSION_DENIED.
#   - Step 3 (Regional GDPR Isolation): Provision separate US (us-central1) and EU (europe-west1)
#     Memory Banks and restrict resource.name by location so a US Retail Agent gets 403 PERMISSION_DENIED
#     if it tries to query the EU Memory Bank.

# Step 3A: Provision a dedicated EU Memory Bank in europe-west1 (paired with us-central1 for US data)
resource "google_vertex_ai_reasoning_engine" "eu_memory_bank" {
  provider     = google-beta
  project      = var.project_id
  region       = "europe-west1"
  display_name = "eu-banking-memory-bank-gdpr"
  spec {
    identity_type = "AGENT_IDENTITY"
  }
}

# Steps 2 & 3B: Enforce both Location (Step 3) and Department memoryScope['lob'] (Step 2) in Cloud IAM
resource "google_project_iam_member" "us_retail_memory_isolation" {
  project = var.project_id
  role    = "roles/aiplatform.memoryUser"
  member  = "serviceAccount:${google_service_account.us_retail_agent.email}"

  condition {
    title      = "US_Retail_Banking_Memory_Isolation"
    expression = "resource.name.startsWith('projects/${local.project_number}/locations/us-central1/reasoningEngines/${local.us_engine_id}') && api.getAttribute('aiplatform.googleapis.com/memoryScope', {})['lob'] == 'retail_banking'"
  }
}

resource "google_project_iam_member" "eu_retail_gdpr_memory_isolation" {
  project = var.project_id
  role    = "roles/aiplatform.memoryUser"
  member  = "serviceAccount:${google_service_account.eu_retail_agent.email}"

  condition {
    title      = "EU_Retail_Banking_GDPR_Memory_Isolation"
    expression = "resource.name.startsWith('projects/${local.project_number}/locations/europe-west1/reasoningEngines/${local.eu_engine_id}') && api.getAttribute('aiplatform.googleapis.com/memoryScope', {})['lob'] == 'retail_banking'"
  }
}
```

## Resources & Links

- **[Agent Platform Memory Bank Overview](https://g.dev/cloud/adventofagents-season3-docs-memory-bank-overview)** — Overview of persistent long-term memory in Gemini Enterprise Agent Platform.
- **[Memory Bank IAM Conditions](https://g.dev/cloud/adventofagents-season3-docs-memory-bank-iam-conditions)** — Restrict which scopes an agent identity can read or write using Cloud IAM Conditions.
- **[Fetch Memories & Exact-Match Scopes](https://g.dev/cloud/adventofagents-season3-docs-memory-bank-fetch-memories)** — How RetrieveMemories enforces exact dictionary matching on scope vs. ListMemories.
- **[Day 15 Kata Demo Repository](https://g.dev/cloud/adventofagents-season3-day15-demo)** — 3-step Memory Bank isolation demo with ADK ToolContext and Cloud IAM Conditions.
