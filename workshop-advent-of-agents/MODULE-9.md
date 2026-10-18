---
season: 3
season_name: "Season 3 — October 2026 (Autumn / Halloween Edition)"
day: 9
title: "Principal Access Boundaries: Contain Blast Radius"
summary: "Enforce a Principal Access Boundary policy to prevent AI agents from accessing cross-project resources even when folder IAM allows it."
tags: ["Phase 2: Agent Boundary", "IAM", "Agent Identity"]
canonical_url: "https://adventofagents.com/2026/10/09"
markdown_url: "https://adventofagents.com/2026/10/09.md"
video_url: "https://www.youtube.com/embed/YDbt7oMdpyc"
primary_video:
  title: "Day 9: Containing Blast Radius with PAB Policies — 5-Minute Google Cloud Kata"
  creator_name: "Erik Jeansson"
  duration: "3:51"
  video_url: "https://www.youtube.com/embed/YDbt7oMdpyc"
---

# 🛡️ Day 9: Principal Access Boundaries: Contain Blast Radius

> **Season 3 — October 2026 (Autumn / Halloween Edition)** · [Interactive Web View](https://adventofagents.com/2026/10/09?utm_source=adventofagents&utm_medium=markdown&utm_campaign=adventofagents_s3_2026&utm_content=day09) · [Raw Markdown](https://adventofagents.com/2026/10/09.md?utm_source=adventofagents&utm_medium=markdown&utm_campaign=adventofagents_s3_2026&utm_content=day09)

**Summary:** Enforce a Principal Access Boundary policy to prevent AI agents from accessing cross-project resources even when folder IAM allows it.

**Day 9 of Google's Advent of Agents — Season 3**

In enterprise environments with hierarchical resource folders, an agent often inherits broad read or write permissions across sibling projects. If a prompt injection or unexpected tool call nudges that agent to query a storage bucket in another team's project, standard IAM allows the request because the inherited folder-level policy says yes, creating a cross-project data exfiltration risk.

**How It Works**

Principal Access Boundaries (PAB) establish a cryptographic perimeter around identities rather than resources. Instead of chasing down every inherited IAM role across your organization, **Principal Access Boundaries (PAB)** wrap an identity perimeter directly around the agent.

For any request to succeed, both the IAM allow policy (what actions the agent can perform) and the Principal Access Boundary (which projects or resources the agent is permitted to touch) must allow it:

- **Identity Perimeter vs. IAM Grants**: Standard IAM allow policies grant capabilities across inherited folders, while a Principal Access Boundary defines the strict allowlist of project boundaries that an agent identity is ever permitted to reach.
- **Cross-Project Lateral Movement Containment**: By binding a Principal Access Boundary policy to your project's Agent Identity principal set, any attempt by the agent to inspect or modify resources in another project is rejected at the cloud control plane with a `403 Forbidden: Principal Access Boundary violation` before any data is touched.

![Principal Access Boundary Blast Radius Containment](/s03/s3-day09-pab-containment.png)

Try it out hands-on from the Github repo below.

**Resources:**

- [Principal Access Boundaries Overview](https://g.dev/cloud/adventofagents-season3-pab)
- [Manage Principal Access Boundary Policies](https://g.dev/cloud/adventofagents-season3-manage-pab-policies)
- [Demo Code Repository](https://g.dev/cloud/adventofagents-season3-pab-demo-repo)

## Code & Commands

### How to Consume These Snippets

```text
======================================================================
  DAY 9 KATA: CONTAINING AGENT BLAST RADIUS WITH PAB POLICIES
======================================================================

WHAT THIS KATA DOES:
Constrains autonomous ADK agents to an identity perimeter using
Principal Access Boundaries (PAB). Even if an agent inherits broad
IAM roles across folders, PAB guarantees it can only touch resources
inside designated projects, blocking cross-project lateral movement.

HOW TO CONSUME THESE SNIPPETS:

1. apply_pab_policy.sh (Infrastructure / Admin Setup)
   - Run these gcloud commands in your shell as an Organization Admin.
   - Replace YOUR_ORGANIZATION_ID and YOUR_PROJECT_ID with your GCP IDs.
   - Creates the organization-level PAB policy and binds it to
     Project 1's SPIFFE Agent Identity principal set.

2. agent.py (ADK Agent Execution & Blast Radius Test)
   - Run or deploy this ADK agent using Python 3.11+.
   - Uses the official Google Cloud Storage MCP server via npx.
   - Test authorized access: Inspect a bucket in Project 1 (succeeds).
   - Test boundary enforcement: Attempt to inspect a bucket in another
     project. The GCP control plane rejects the call with:
     "403 Forbidden: Principal Access Boundary violation".

Full reproduction repo with automated setup & teardown:
https://github.com/jeansson-01/gcp-pab-for-agent-identity
```

### Enforce PAB Policy on Agent Identities

```bash
export CLOUDSDK_METRICS_ENVIRONMENT="advent-of-agents-s3-day09"

# 1. Export required environment variables
export ORG_ID="YOUR_ORGANIZATION_ID"
export PROJECT_1_ID="YOUR_PROJECT_ID"
export PROJECT_1_NUMBER=$(gcloud projects describe "${PROJECT_1_ID}" --format="value(projectNumber)")

# 2. Create Organization-level Principal Access Boundary (PAB) Policy
gcloud iam principal-access-boundary-policies create "pab-agent-containment-policy" \
  --organization="${ORG_ID}" \
  --location="global" \
  --display-name="PAB Agent Containment Policy" \
  --details-rules='[{"description":"Allow access ONLY to Project 1","effect":"ALLOW","resources":["//cloudresourcemanager.googleapis.com/projects/'"${PROJECT_1_ID}"'"]}]'

# 3. Target Project 1 Agent Identities principal set (SPIFFE-based)
AGENT_PRINCIPAL_SET="//agents.global.org-${ORG_ID}.system.id.goog/attribute.container/projects/${PROJECT_1_NUMBER}"

# 4. Bind PAB Policy to Project 1 Agent Identities
gcloud iam policy-bindings create "bind-pab-agent-containment" \
  --project="${PROJECT_1_ID}" \
  --location="global" \
  --display-name="Bind PAB to Project 1 Agent Identities" \
  --policy="organizations/${ORG_ID}/locations/global/principalAccessBoundaryPolicies/pab-agent-containment-policy" \
  --target-principal-set="${AGENT_PRINCIPAL_SET}"

# 5. Verify boundary enforcement status
gcloud iam policy-bindings describe "bind-pab-agent-containment" \
  --project="${PROJECT_1_ID}" \
  --location="global" \
  --format="yaml(name,policy,target)"
```

### ADK Agent with Cloud Storage MCP Toolset

```python
import os
from google.adk.agents import Agent
from google.adk.tools.mcp_tool import McpToolset
from google.adk.tools.mcp_tool.mcp_session_manager import StdioConnectionParams
from mcp import StdioServerParameters

AGENT_INSTRUCTION = """
You are the Cloud Storage Security Inspector Agent deployed in Google Cloud Agent Runtime.
Your primary role is to inspect Google Cloud Storage (GCS) buckets and list their objects using the Google Cloud Storage MCP tools.

Guidelines:
1. When asked to inspect or list objects in a bucket (e.g. 'gs://bucket-name'), call the MCP tool 'list_objects'.
2. If access succeeds, summarize the objects found clearly.
3. If access fails (e.g. 403 Forbidden or Principal Access Boundary violation), report the exact error message.
"""

storage_mcp_toolset = McpToolset(
    connection_params=StdioConnectionParams(
        server_params=StdioServerParameters(
            command="npx",
            args=["-y", "@google-cloud/storage-mcp"],
            env={
                "PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"),
                "HOME": os.environ.get("HOME", "/root"),
            },
        )
    ),
    tool_filter=["list_objects", "list_buckets", "get_object_metadata"],
)

root_agent = Agent(
    name="pab_storage_inspector",
    model="gemini-3.1-pro",
    instruction=AGENT_INSTRUCTION,
    tools=[storage_mcp_toolset],
)
```

## Resources & Links

- **[PAB Agent Containment Demo Repository](https://g.dev/cloud/adventofagents-season3-pab-demo-repo)** — Complete reference implementation and automated reproduction scripts for Principal Access Boundaries with ADK.
- **[Principal Access Boundaries overview](https://g.dev/cloud/adventofagents-season3-pab)** — Define an identity perimeter that limits which resources principals can access regardless of IAM allow policies.
- **[Manage PAB policies](https://g.dev/cloud/adventofagents-season3-manage-pab-policies)** — Create, evaluate, and bind Principal Access Boundary policies using gcloud CLI.
- **[Agent Identity overview](https://g.dev/cloud/adventofagents-season3-gemini-enterprise-agent-identity)** — Cryptographic SPIFFE machine identities for autonomous agents running in Agent Runtime.
