---
season: 3
season_name: "Season 3 — October 2026 (Autumn / Halloween Edition)"
day: 5
title: "Agent Identity: One SPIFFE ID Per Agent"
summary: "Deploy an agent with its own cryptographic SPIFFE identity, grant permissions to the identity and verify it."
tags: ["Phase 2: Agent Auth n/z", "IAM", "Security"]
canonical_url: "https://adventofagents.com/2026/10/05"
markdown_url: "https://adventofagents.com/2026/10/05.md"
video_url: "https://www.youtube.com/embed/0z7kizuaB0M"
primary_video:
  title: "Day 5: Give Every Agent an Identity (SPIFFE) — 5-Minute Google Cloud Kata"
  creator_name: "Sita Lakshmi Sangameswaran"
  duration: "10:21"
  video_url: "https://www.youtube.com/embed/0z7kizuaB0M"
---

# 🪪 Day 5: Agent Identity: One SPIFFE ID Per Agent

> **Season 3 — October 2026 (Autumn / Halloween Edition)** · [Interactive Web View](https://adventofagents.com/2026/10/05?utm_source=adventofagents&utm_medium=markdown&utm_campaign=adventofagents_s3_2026&utm_content=day05) · [Raw Markdown](https://adventofagents.com/2026/10/05.md?utm_source=adventofagents&utm_medium=markdown&utm_campaign=adventofagents_s3_2026&utm_content=day05)

**Summary:** Deploy an agent with its own cryptographic SPIFFE identity, grant permissions to the identity and verify it.

**Day 5 of Google's Advent of Agents — Season 3**

Three agents in your project share one service account. One of them just read a bucket of customer records. Which one was it? With a shared principal you cannot answer that, because all three sign their requests as the same identity. Every governance control in this series sits on top of the answer to that question, so Day 5 fixes the identity layer.

**Why should you use Agent Identity and not a Service Account?**

- **Service account**: A shared workload identity. Many agents can run under one service account, anyone with the right role can impersonate it, and a developer can download a JSON key that never expires. One principal, many possible actors, no way to tell them apart afterward. Also, impossible to assign right permissions when different agents require different levels of access.
- **Agent Identity**: A SPIFFE ID minted for a single agent at deploy time and tied to the agent's lifecycle. It cannot be shared between workloads, impersonated, or exported as a key file.

There's also another complementary identity type which we'll explore in Day 6:
- **User identity**: The human who asked. An agent borrows this through delegation instead of holding the user's credential.

**How to obtain an Agent Identity?**

1. **Turn it on**: Deploy an agent with `identity_type=AGENT_IDENTITY`. Agent Runtime/ Cloud Run issues the SPIFFE ID and an X.509 certificate it rotates every 24 hours, so there is no key material for you to store or leak.
2. **Grant to the agent, not the account**: The agent is now the principal itself, so any IAM role (such as `roles/storage.objectViewer`) granted on its `principal://` identifier is assigned exactly to that agent.
3. **Verify who acted**: The next time the agent accesses any cloud resource, filter Cloud Logging by that resource using `protoPayload.resourceName`, then look at the `principalSubject` field on the results. It holds the acting agent's SPIFFE ID, so "which agent did this" becomes straightforward to answer.

![Shared Service Account vs Per-Agent SPIFFE Identity](/s03/s3-day05-agent-identity.png)

**Resources:**
- [Agent Identity Quickstart with ADK](https://g.dev/cloud/adventofagents-season3-agent-identity-quickstart)
- [Codelab: Agent Identity and Auth Manager](https://g.dev/cloud/adventofagents-season3-agent-identity-authmanager-codelab)

## Code & Commands

```bash
export CLOUDSDK_METRICS_ENVIRONMENT="advent-of-agents-s3-day05"

# STEP 1 - Install the CLI and scaffold a prototype agent project.
uvx google-agents-cli setup
agents-cli create my-first-agent --prototype --yes
cd my-first-agent

# STEP 2 - Manual edit. Replace app/agent.py with the agent.py shown below.
# It adds a BigQuery toolset so the agent can list datasets and run queries.

# STEP 3 - Install dependencies and add Agent Runtime as the deployment target.
agents-cli install
agents-cli scaffold enhance . --deployment-target agent_runtime --prototype --yes

# STEP 4 - Deploy. --agent-identity is the flag that matters today. Without it the
# agent runs as a shared service account. With it, Agent Runtime mints a SPIFFE ID
# for this agent alone, plus an X.509 certificate it rotates every 24 hours.
agents-cli deploy --agent-identity --project YOUR_PROJECT_ID --region us-central1
```

```python
import datetime
from zoneinfo import ZoneInfo

import google.auth
from google.adk.agents import Agent
from google.adk.apps import App
from google.adk.integrations.bigquery import BigQueryCredentialsConfig, BigQueryToolset
from google.adk.models import Gemini
from google.genai import types


MODEL = "gemini-3.8-flash"

credentials, _ = google.auth.default()
bigquery_toolset = BigQueryToolset(
    credentials_config=BigQueryCredentialsConfig(credentials=credentials),
)


def get_weather(query: str) -> str:
    """Simulates a web search. Use it get information on weather.

    Args:
        query: A string containing the location to get weather information for.

    Returns:
        A string with the simulated weather information for the queried location.
    """
    if "sf" in query.lower() or "san francisco" in query.lower():
        return "It's 60 degrees and foggy."
    return "It's 90 degrees and sunny."


def get_current_time(query: str) -> str:
    """Simulates getting the current time for a city.

    Args:
        city: The name of the city to get the current time for.

    Returns:
        A string with the current time information.
    """
    if "sf" in query.lower() or "san francisco" in query.lower():
        tz_identifier = "America/Los_Angeles"
    else:
        return f"Sorry, I don't have timezone information for query: {query}."

    tz = ZoneInfo(tz_identifier)
    now = datetime.datetime.now(tz)
    return f"The current time for query {query} is {now.strftime('%Y-%m-%d %H:%M:%S %Z%z')}"


root_agent = Agent(
    name="root_agent",
    model=Gemini(
        model=MODEL,
        retry_options=types.HttpRetryOptions(attempts=3),
    ),
    instruction="You are a helpful AI assistant designed to provide accurate and useful information.",
    tools=[get_weather, get_current_time, bigquery_toolset],
)

app = App(
    root_agent=root_agent,
    name="app",
)
```

```bash
export CLOUDSDK_METRICS_ENVIRONMENT="advent-of-agents-s3-day05"

# Creates the data the agent will query. Run this before you prompt the agent.

# STEP 5 - Grab your current gcloud project ID
PROJECT_ID=$(gcloud config get-value project)

# STEP 6 - Create a sample dataset named "sample_data"
bq --location=US mk --dataset "${PROJECT_ID}:sample_data"

# STEP 7 - Create a sample table ("cities_weather") with 3 rows of data
bq query --use_legacy_sql=false \
"CREATE OR REPLACE TABLE \`${PROJECT_ID}.sample_data.cities_weather\` AS
SELECT 'San Francisco' AS city, 'CA' AS state, 60 AS temp_f, 'Foggy' AS condition UNION ALL
SELECT 'New York'      AS city, 'NY' AS state, 75 AS temp_f, 'Sunny' AS condition UNION ALL
SELECT 'Seattle'       AS city, 'WA' AS state, 58 AS temp_f, 'Rainy' AS condition;"

# STEP 8 - Verify that the table was created
bq head "${PROJECT_ID}:sample_data.cities_weather";
```

```bash
export CLOUDSDK_METRICS_ENVIRONMENT="advent-of-agents-s3-day05"

# STEP 9 - Confirm the agent has an identity of its own.
# In the console, open Agent Platform > Deployments and find my-first-agent.
# The **Identity** column shows a SPIFFE principal instead of a service account:
#
#   principal://agents.global.org-ORG_ID.system.id.goog/resources/aiplatform/projects/PROJECT_NUMBER/locations/us-central1/reasoningEngines/ENGINE_ID
#
# Read the same value from the command line:

gcloud ai reasoning-engines describe ENGINE_ID \
  --project=PROJECT_ID --location=us-central1 \
  --format="value(spec.effectiveIdentity)"

# STEP 10 - Watch it fail before granting anything.
# Send this prompt in the Playground:

Run a SQL query on sample_data.cities_weather in project "YOUR_PROJECT_ID" to return all rows

# It fails. A new agent identity holds only its default roles, so it cannot
# read your data until you say so. That default is the whole point of today.


# STEP 11 - Grant the two roles to the agent, not to a service account.

AGENT=$(gcloud ai reasoning-engines describe ENGINE_ID \
  --project=PROJECT_ID --location=us-central1 \
  --format="value(spec.effectiveIdentity)")

gcloud projects add-iam-policy-binding PROJECT_ID \
  --member="principal://${AGENT}" \
  --role="roles/bigquery.jobUser"

gcloud projects add-iam-policy-binding PROJECT_ID \
  --member="principal://${AGENT}" \
  --role="roles/bigquery.dataViewer"

# The console equivalent is navigating to the IAM and granting
# "BigQuery Job User" and "BigQuery Data Viewer" to the agent's identity.


# STEP 12 - Send the same prompt again.
# All three rows come back. Nothing about the agent changed, only what its
# identity is allowed to reach.


# STEP 13 - Prove which agent made the call.
# In Cloud Logging, filter by the resource that was read:

protoPayload.resourceName:"datasets/sample_data"

# Then read principalSubject on the matching entries. It holds the agent's
# SPIFFE ID, not a shared service account.
```

## Resources & Links

- **[Agent Identity overview](https://g.dev/cloud/adventofagents-season3-gemini-enterprise-agent-identity)** — SPIFFE identity format, credentials, and how it compares to service accounts.
- **[Agent Identity with Agent Runtime](https://g.dev/cloud/adventofagents-season3-agent-identity-runtime)** — Deploy with identity_type, grant IAM, and handle CI/CD redeploys.
- **[Agent Identity with Cloud Run](https://g.dev/cloud/adventofagents-season3-agent-identity-cloud-run)** — Deploy a Cloud Run instance with Agent Identity
- **[Create and deploy an agent with Agents CLI](https://g.dev/cloud/adventofagents-season3-agent-identity-quickstart)** — End-to-end quickstart that provisions the SPIFFE identity.
