---
season: 3
season_name: "Season 3 — October 2026 (Autumn / Halloween Edition)"
day: 6
title: "Token Delegation: Agent acts on-behalf-of the user"
summary: "Give your agent access to external tools, APIs, or services as the signed-in user, so it only sees the records that user is allowed to see."
tags: ["Phase 2: Agent Auth n/z", "OAuth", "Security", "Auth Manager"]
canonical_url: "https://adventofagents.com/2026/10/06"
markdown_url: "https://adventofagents.com/2026/10/06.md"
video_url: "https://www.youtube.com/embed/Y9oiy_Szf0I"
primary_video:
  title: "Day 6: Act on Behalf of the User (Token Delegation) — 5-Minute Google Cloud Kata"
  creator_name: "Sita Lakshmi Sangameswaran"
  duration: "8:26"
  video_url: "https://www.youtube.com/embed/Y9oiy_Szf0I"
---

# 🎫 Day 6: Token Delegation: Agent acts on-behalf-of the user

> **Season 3 — October 2026 (Autumn / Halloween Edition)** · [Interactive Web View](https://adventofagents.com/2026/10/06?utm_source=adventofagents&utm_medium=markdown&utm_campaign=adventofagents_s3_2026&utm_content=day06) · [Raw Markdown](https://adventofagents.com/2026/10/06.md?utm_source=adventofagents&utm_medium=markdown&utm_campaign=adventofagents_s3_2026&utm_content=day06)

**Summary:** Give your agent access to external tools, APIs, or services as the signed-in user, so it only sees the records that user is allowed to see.

**Day 6 of Google's Advent of Agents — Season 3**

Imagine, two people ask your support agent the same question: "show me my open tickets." They both get the same list, because the agent holds one API token for Jira and that token sees every ticket in the instance. Telling the model to *filter by user in the system prompt* is not access control, it is a suggestion. The agent needs to call Jira as the person who asked.

Calling a third party tool as the user means obtaining an OAuth token for that specific person and keeping it somewhere safe. Agent Identity auth manager does both.

*"It stores your OAuth client secret, runs the consent flow, holds the resulting per-user token in a Google-managed vault, and refreshes it when it expires."*

The third party tool then applies the access rules it already enforces for that person, so the agent inherits their permissions and nothing more, and your agent code never touches the client secret.

This builds on the agent identity from Day 5. The agent authenticates to auth manager as itself using its SPIFFE ID, then borrows the user's authority for the outbound call, so both identities show up in the audit trail.

**How to set up user delegation?**

You need an agent already deployed, plus a client ID and client secret from the third-party OAuth provider you want to reach (Jira, GitHub, Salesforce, and so on).

1. **Create the auth provider**: Run `gcloud agent-identity auth-providers create` with the client ID, client secret, authorization URL, and token URL obtained from the third-party app.
2. **Register the callback URI**: Auth manager generates a callback URI. Add it to your OAuth client in the third-party developer portal. Failing to do it will error with a redirect mismatch.
3. **Grant the agent**: Give the agent's SPIFFE ID `roles/agentidentity.user` on the auth provider resource.
4. **Grant yourself**: Give your own account the same role, or local runs fail with a 403 on `agentidentity.authProviders.retrieveCredentials`.
5. **Try it**: Run the sample UI client and send a prompt that hits the tool. You are asked to sign in and consent once, and the agent fetches your data.

![Per-User Token Delegation with Agent Identity Auth Manager](/s03/s3-day06-token-delegation.png)

**What happens under the hood? 👻**

On the first tool call, ADK returns an `adk_request_credential` function call carrying an `auth_uri`. Your app opens it, the user consents, and your `continue_uri` handler finalizes the credential. Auth manager stores the token and reuses it on later calls. On every later tool invocation, ADK fetches the credential and sets the `Authorization` header for you. Each fetch is logged as a `RetrieveCredentials` call attributed to the agent.

Use the runnable sample UI server in the [adk-python repository](https://github.com/google/adk-python/tree/main/contributing/samples/integrations/gcp_auth/client?utm_source=adventofagents&utm_medium=markdown&utm_campaign=adventofagents_s3_2026&utm_content=day06), or write a [custom client following these instructions](https://docs.cloud.google.com/iam/docs/auth-with-3lo-v2?utm_source=adventofagents&utm_medium=markdown&utm_campaign=adventofagents_s3_2026&utm_content=day06#custom-ui-application).

To learn more about what the client app does and how it works, refer to the codelab link below 👇.

**Resources:**
- [3-legged OAuth Quickstart with ADK](https://g.dev/cloud/adventofagents-season3-agent-identity-auth-manager)
- 👉 **Try it out**: [Codelab: Agent Identity and Auth Manager](https://g.dev/cloud/adventofagents-season3-agent-identity-authmanager-codelab)

## Code & Commands

```bash
export CLOUDSDK_METRICS_ENVIRONMENT="advent-of-agents-s3-day06"

# PREREQ - Google Cloud CLI 586.0.0 or newer.
gcloud components update

# PREREQ - Enable the APIs.
gcloud services enable     agentidentity.googleapis.com     agentregistry.googleapis.com     aiplatform.googleapis.com     apphub.googleapis.com     --project=YOUR_PROJECT_ID

# STEP 1 - Install the CLI and scaffold a prototype agent project.
uvx google-agents-cli setup
agents-cli create auth-manager-demo --prototype --yes
cd auth-manager-demo

# STEP 2 - Manual edit. Replace app/agent.py with the agent.py shown below.
# STEP 3 - Manual edit. Add a new app/tools.py with the tools.py shown below.

# STEP 4 - Add the two google-adk extras this agent needs.
# In pyproject.toml, change the google-adk line to:
#   "google-adk[agent-identity,gcp,mcp,otel-gcp]>=2.5.0,<3.0.0",
agents-cli install

# STEP 5 - Deploy with Agent Identity.
echo '{ "identity_type": "AGENT_IDENTITY" }' > app/.agent_engine_config.json

uv export --no-emit-workspace --no-hashes --format requirements.txt     --output-file app/requirements.txt

uv run adk deploy agent_engine app     --project="YOUR_PROJECT_ID"     --region="us-central1"

# Note the reasoningEngines/ENGINE_ID it prints. Your agent's SPIFFE identity is:
#   principal://agents.global.org-ORG_ID.system.id.goog/resources/aiplatform/projects/PROJECT_NUMBER/locations/us-central1/reasoningEngines/ENGINE_ID
# You need it for the IAM binding below.
```

```txt
# STEP 6: Create the auth provider. The client ID and secret come later: GitHub
# will not issue them until it knows this provider's callback URL.
gcloud agent-identity auth-providers create github-oauth-provider     --project="YOUR_PROJECT_ID"     --location="us-central1"     --three-legged-oauth-authorization-url="https://github.com/login/oauth/authorize"     --three-legged-oauth-token-url="https://github.com/login/oauth/access_token"

# STEP 7: Read the generated callback URL back off the provider.
gcloud agent-identity auth-providers describe github-oauth-provider     --project="YOUR_PROJECT_ID"     --location="us-central1"

# Copy the redirectUrl field from the output - it is nested under
# authProviderTypeParams.threeLeggedOauth.
# To grab it directly:
gcloud agent-identity auth-providers describe github-oauth-provider     --project="YOUR_PROJECT_ID" --location="us-central1"     --format="value(authProviderTypeParams.threeLeggedOauth.redirectUrl)"

# It looks like:
# https://agentidentitycredentials.googleapis.com/v1/projects/YOUR_PROJECT_ID/locations/us-central1/authProviders/github-oauth-provider/oauthcallback

# STEP 8: Register the OAuth app on GitHub. Go to [GitHub Developer Settings](https://github.com/settings/developers) and
# click "Register a new OAuth app".
- Homepage URL: the URL of your frontend application (http://localhost:8501 while prototyping locally; swap in your deployed URL later).
- Authorization callback URL: the redirectUrl from STEP 2, copied exactly.
- Click "Register application", then "Generate a new client secret", and save both the Client ID and Client Secret.

# STEP 9: Update the Auth Provider with the GitHub credentials.
gcloud agent-identity auth-providers update github-oauth-provider     --location="us-central1"     --three-legged-oauth-client-id="YOUR_CLIENT_ID"     --three-legged-oauth-client-secret="YOUR_CLIENT_SECRET"

# STEP 10: Grant the agent permission to read credentials from the auth provider. Substitute the
# SPIFFE identity you noted at deploy time, including its principal:// prefix.
gcloud agent-identity auth-providers add-iam-policy-binding github-oauth-provider     --project="YOUR_PROJECT_ID"     --location="us-central1"     --role="roles/agentidentity.user"     --member="principal://REPLACE_WITH_AGENT_IDENTITY"

# STEP 11: Grant yourself the same role, to test locally for this demo.
gcloud agent-identity auth-providers add-iam-policy-binding github-oauth-provider     --project="YOUR_PROJECT_ID"     --location="us-central1"     --role="roles/agentidentity.user"     --member="user:YOUR_EMAIL_ADDRESS"

# STEP 12: Run the sample UI client and send a prompt.
cd ../
git clone --depth 1 https://github.com/google/adk-python.git
cd adk-python/contributing/samples/integrations/gcp_auth/client
uv venv --python 3.13 .venv
uv pip install --python .venv/bin/python -r requirements.txt

# Substitute project ID and engine ID.
export GOOGLE_CLOUD_PROJECT=YOUR_PROJECT_ID
export GOOGLE_CLOUD_LOCATION=us-central1
export AGENT_ID=ENGINE_ID_FROM_STEP_5
.venv/bin/uvicorn main:app --port 8501

# Open http://localhost:8501 - Enter your project ID and region. Load the Remote Agents from your project. Then select the agent that you deployed from the dropdown. Click "Save & Apply Settings", then prompt.
# The first tool call opens a GitHub consent screen. After you approve it, the
# agent reads your private repos with your token, so it sees exactly what you
# can see and nothing else.

Example prompt: "List my contribution across my private github repositories over the last 3 months."
The agent makes the call using your credentials to fetch data that only you can see.
```

```python
from google.adk.agents import Agent
from google.adk.apps import App
from google.adk.models import Gemini
from google.genai import types

from app.tools import github_toolset

import os
import google.auth

_, project_id = google.auth.default()
os.environ["GOOGLE_CLOUD_PROJECT"] = project_id
os.environ["GOOGLE_CLOUD_LOCATION"] = "global"
os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "True"

INSTRUCTION = """You are the DevOps Assistant. You help developers list and triage their GitHub issues and pull requests.
Your capabilities: You have a GitHub MCP toolset that you can use to perform actions that the user requests.

Rules:
- NEVER write, update, or delete. You are only allowed read access.
- Act on behalf of the signed-in user.
- If a tool returns an authentication or authorization error, guide the user to sign in.
- NEVER fabricate information. Only report real issues returned by tools.
"""

root_agent = Agent(
    name="root_agent",
    model=Gemini(
        model="gemini-3.8-flash",
        retry_options=types.HttpRetryOptions(attempts=3),
    ),
    instruction=INSTRUCTION,
    tools=[github_toolset()],
)

app = App(
    root_agent=root_agent,
    name="app",
)
```

```python
from __future__ import annotations
import os
from google.adk.auth.credential_manager import CredentialManager
from google.adk.integrations.agent_identity import GcpAuthProvider, GcpAuthProviderScheme
from google.adk.tools.mcp_tool import McpToolset
from google.adk.tools.mcp_tool.mcp_session_manager import StreamableHTTPConnectionParams

import google.auth
_, project_id = google.auth.default()

# 1. Register the GCP Auth Provider in the global Credential Manager
CredentialManager.register_auth_provider(GcpAuthProvider())

# 2. The auth provider you created with gcloud. The project is resolved above;
# change the location and name here if you used different ones.
OAUTH_PROVIDER_NAME = f"projects/{project_id}/locations/us-central1/authProviders/github-oauth-provider"

# 3. Where GitHub sends the user after they consent. Your app must serve this
# route and finalize the credential; it has to match the callback URL you
# registered on GitHub. Overridable per environment.
OAUTH_CONTINUE_URI = os.environ.get(
    "OAUTH_CONTINUE_URI", 
    "http://localhost:8501/validateUserId"
)

def github_toolset() -> McpToolset:
    """Returns the McpToolset using 3LO credentials retrieved via GCP Auth Manager."""
    auth_scheme = GcpAuthProviderScheme(
        name=OAUTH_PROVIDER_NAME,
        scopes=["repo"],
        continue_uri=OAUTH_CONTINUE_URI,
    )
    return McpToolset(
        connection_params=StreamableHTTPConnectionParams(
            url="https://api.githubcopilot.com/mcp/",
            headers={
                "X-MCP-Toolsets": "all",
                "X-MCP-Readonly": "true",
            },
        ),
        auth_scheme=auth_scheme,
    )
```

## Resources & Links

- **[3-legged OAuth with auth manager](https://g.dev/cloud/adventofagents-season3-agent-identity-auth-manager)** — Full setup: provider creation, callback URI, consent handling, and deployment.
- **[Auth Manager Codelab](https://g.dev/cloud/adventofagents-season3-agent-identity-authmanager-codelab)** — Hands-on codelab to setup Agent Identity and Auth Manager.
