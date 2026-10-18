---
season: 3
season_name: "Season 3 — October 2026 (Autumn / Halloween Edition)"
day: 7
title: "Offline Delegation: Acting for Users While They Sleep"
summary: "Execute unattended background agent jobs using scoped offline refresh tokens in Agent Identity Auth Manager or Cloud Secret Manager without live user sessions or super-admin rights."
tags: ["Phase 2: Agent Auth n/z", "OAuth", "Auth Manager", "Secret Manager"]
canonical_url: "https://adventofagents.com/2026/10/07"
markdown_url: "https://adventofagents.com/2026/10/07.md"
video_url: "https://www.youtube.com/embed/fuxdAw4S13I"
primary_video:
  title: "Day 7: Offline & Asynchronous Agent Workflows — Programmatic Token Delegation"
  creator_name: "Daniel Lees"
  duration: "6:04"
  video_url: "https://www.youtube.com/embed/fuxdAw4S13I"
---

# 🔐 Day 7: Offline Delegation: Acting for Users While They Sleep

> **Season 3 — October 2026 (Autumn / Halloween Edition)** · [Interactive Web View](https://adventofagents.com/2026/10/07?utm_source=adventofagents&utm_medium=markdown&utm_campaign=adventofagents_s3_2026&utm_content=day07) · [Raw Markdown](https://adventofagents.com/2026/10/07.md?utm_source=adventofagents&utm_medium=markdown&utm_campaign=adventofagents_s3_2026&utm_content=day07)

**Summary:** Execute unattended background agent jobs using scoped offline refresh tokens in Agent Identity Auth Manager or Cloud Secret Manager without live user sessions or super-admin rights.

**Day 7 of Google's Advent of Agents — Season 3**

In Day 6, your agent acted on behalf of a signed-in user by opening a browser consent prompt. That works when a human is at their keyboard, but fails for scheduled background jobs like a 2:00 AM incident summarizer running while the user is asleep. Giving a background agent a shared "super-admin" API key to bypass the login prompt breaks least-privilege security, because the agent can now read everyone's data instead of just the person who scheduled the job.

You solve this with **Offline Token Delegation**. While the user is online, they grant consent once with the `offline_access` scope, storing a long-lived **refresh token** in a secure vault. When the 2:00 AM job runs, the agent uses two layers of identity: it authenticates to the vault using its own cryptographic **Agent Identity** (from Day 5), and exchanges the user's stored refresh token for a short-lived access token scoped strictly to that user's permissions.

![Offline Token Delegation for Background Agents](/s03/s3-day07-offline-delegation.png)

The code tabs compare the two ways to vault and refresh these offline tokens in your agent:

- **Cloud Secret Manager (Manual Vault & Rotation)**: In `secret_manager_offline_agent.py`, your agent authenticates to Secret Manager with its Agent Identity, exchanges the user's `refresh_token` at the OAuth provider for a 15-minute `access_token`, writes the newly rotated refresh token as a new secret version, and disables the old version so stolen tokens cannot be reused.
- **Agent Identity Auth Manager (Managed Vault & Auto-Rotation)**: Offloads secret storage, token exchange, and refresh rotation to Google's managed broker. You can either call `retrieve_credentials()` inside a custom function tool or attach `GcpAuthProviderScheme` to an `McpToolset` so Auth Manager injects the refreshed `Authorization` header automatically.

**Resources:**

- [Agent Identity Auth Manager Overview](https://g.dev/cloud/adventofagents-season3-day6-docs-authmanager)
- [Authenticate Using 3-Legged OAuth with Auth Manager](https://g.dev/cloud/adventofagents-season3-agent-identity-auth-manager)
- [Cloud Secret Manager Documentation](https://g.dev/cloud/adventofagents-season3-day6-docs-secret-manager)
- [OAuth 2.0 Offline Access & Refresh Tokens](https://datatracker.ietf.org/doc/html/rfc6749#section-6)

## Code & Commands

### 1. DIY Vault & Rotation (Secret Manager)

```python
import os
import google.auth
import requests
from google.cloud import secretmanager
from google.adk.agents import Agent
from google.adk.apps import App
from google.adk.models import Gemini
from google.genai import types

_, project_id = google.auth.default()
os.environ["GOOGLE_CLOUD_PROJECT"] = project_id
os.environ["GOOGLE_CLOUD_LOCATION"] = "global"
os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "True"

def get_delegated_access_token() -> str:
    """Exchange a vaulted offline_access refresh token for a short-lived access token."""
    client = secretmanager.SecretManagerServiceClient()
    project_id = os.environ["GOOGLE_CLOUD_PROJECT"]
    secret_parent = f"projects/{project_id}/secrets/agent-refresh-token"

    # Layer 1: Authenticate via Agent Identity (SPIFFE) to read the latest vaulted token
    current = client.access_secret_version(name=f"{secret_parent}/versions/latest")
    refresh_token = current.payload.data.decode("UTF-8").strip()

    # Layer 2: Exchange the refresh token for a 15-minute down-scoped access token.
    # Note: OAUTH_CLIENT_SECRET is in os.environ strictly to illustrate the raw OAuth
    # exchange; in production, vault client credentials or use Auth Manager (Tab 2 & 3).
    response = requests.post(
        os.environ["IDP_TOKEN_URL"],
        data={
            "grant_type": "refresh_token",
            "client_id": os.environ["OAUTH_CLIENT_ID"],
            "client_secret": os.environ["OAUTH_CLIENT_SECRET"],
            "refresh_token": refresh_token,
        },
        timeout=10,
    )
    response.raise_for_status()
    token_data = response.json()

    # Rotate the refresh token in Secret Manager and disable the prior version
    if "refresh_token" in token_data:
        client.add_secret_version(
            parent=secret_parent,
            payload={"data": token_data["refresh_token"].encode("UTF-8")},
        )
        client.disable_secret_version(name=current.name)

    return token_data["access_token"]

def fetch_overnight_reports() -> dict:
    """Fetch only the delegating user's authorized reports using the ephemeral token."""
    token = get_delegated_access_token()
    res = requests.get(
        os.environ["REPORTS_API_URL"],
        headers={"Authorization": f"Bearer {token}"},
        timeout=10,
    )
    res.raise_for_status()
    return res.json()

# Hydrate ADK runtime for unattended overnight execution
root_agent = Agent(
    name="overnight_batch_summarizer",
    model=Gemini(
        model="gemini-3.8-flash",
        retry_options=types.HttpRetryOptions(attempts=3),
    ),
    instruction="Summarize the user's overnight incident reports concisely.",
    tools=[fetch_overnight_reports],
)
app = App(
    name="overnight_batch_summarizer_app",
    root_agent=root_agent,
)
```

### 2. Managed Broker (Auth Manager API)

```python
import os
import google.auth
import requests
from google.adk.agents import Agent
from google.adk.apps import App
from google.adk.models import Gemini
from google.adk.tools import ToolContext
from google.cloud.agentidentitycredentials_v1 import (
    AuthProviderCredentialsServiceClient,
    RetrieveCredentialsRequest,
)
from google.genai import types

_, project_id = google.auth.default()
os.environ["GOOGLE_CLOUD_PROJECT"] = project_id
os.environ["GOOGLE_CLOUD_LOCATION"] = "global"
os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "True"

OAUTH_PROVIDER = (
    f"projects/{project_id}/locations/us-central1/authProviders/reports-oauth-provider"
)

def fetch_overnight_reports(tool_context: ToolContext) -> dict:
    """Headlessly fetch the offline user's auto-refreshed OAuth token from Auth Manager."""
    # Layer 1 & 2: Authenticate via SPIFFE Agent Identity (roles/agentidentity.user).
    # Auth Manager looks up tool_context.user_id's vaulted offline_access refresh_token,
    # automatically exchanges/rotates it at the IdP, and returns a fresh access_token.
    client = AuthProviderCredentialsServiceClient(transport="rest")
    cred_response = client.retrieve_credentials(
        RetrieveCredentialsRequest(
            auth_provider=OAUTH_PROVIDER,
            user_id=tool_context.user_id,  # e.g., "alice@example.com" from cron job
            scopes=["offline_access", "reports:read"],
        )
    )
    token = cred_response.success.token

    res = requests.get(
        os.environ["REPORTS_API_URL"],
        headers={"Authorization": f"Bearer {token}"},
        timeout=10,
    )
    res.raise_for_status()
    return res.json()

root_agent = Agent(
    name="overnight_batch_summarizer",
    model=Gemini(
        model="gemini-3.8-flash",
        retry_options=types.HttpRetryOptions(attempts=3),
    ),
    instruction="Summarize the user's overnight incident reports concisely.",
    tools=[fetch_overnight_reports],
)
app = App(
    name="overnight_batch_summarizer_app",
    root_agent=root_agent,
)
```

### 3. Zero-Boilerplate MCP (Auth Manager + ADK)

```python
import os
import google.auth
from google.adk.agents import Agent
from google.adk.apps import App
from google.adk.auth.credential_manager import CredentialManager
from google.adk.integrations.agent_identity import GcpAuthProvider, GcpAuthProviderScheme
from google.adk.models import Gemini
from google.adk.tools.mcp_tool import McpToolset
from google.adk.tools.mcp_tool.mcp_session_manager import StreamableHTTPConnectionParams
from google.genai import types
from vertexai import agent_engines

_, project_id = google.auth.default()
os.environ["GOOGLE_CLOUD_PROJECT"] = project_id
os.environ["GOOGLE_CLOUD_LOCATION"] = "global"
os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "True"

# Deployed on Agent Engine with {"identity_type": "AGENT_IDENTITY"}
CredentialManager.register_auth_provider(GcpAuthProvider())

reports_mcp = McpToolset(
    connection_params=StreamableHTTPConnectionParams(
        url=os.environ["REPORTS_MCP_URL"],
        headers={"X-MCP-Readonly": "true"},
    ),
    # GcpAuthProvider reads context.user_id from the headless invocation below,
    # refreshes that user's vaulted offline_access token in Auth Manager, and
    # injects the Authorization: Bearer header automatically.
    auth_scheme=GcpAuthProviderScheme(
        name=os.environ["REPORTS_AUTH_PROVIDER"],
        scopes=["offline_access", "reports:read"],
    ),
)

root_agent = Agent(
    name="overnight_batch_summarizer",
    model=Gemini(
        model="gemini-3.8-flash",
        retry_options=types.HttpRetryOptions(attempts=3),
    ),
    instruction="Summarize the user's overnight incident reports concisely.",
    tools=[reports_mcp],
)
app = App(name="overnight_batch_summarizer_app", root_agent=root_agent)

# Unattended 2:00 AM Cloud Scheduler / Cloud Run trigger acting on behalf of Alice:
async def run_overnight_job(target_user_id: str = "alice@example.com") -> None:
    remote_app = agent_engines.get(os.environ["AGENT_ENGINE_RESOURCE_NAME"])
    async for event in remote_app.async_stream_query(
        user_id=target_user_id,  # Binds context.user_id for headless Auth Manager lookup
        message="Generate my overnight incident report summary.",
    ):
        print(event)
```

## Resources & Links

- **[Agent Identity Auth Manager Overview](https://g.dev/cloud/adventofagents-season3-day6-docs-authmanager)** — Managed credential vault architecture and automated OAuth token refreshes for agents.
- **[3-Legged OAuth with Auth Manager](https://g.dev/cloud/adventofagents-season3-agent-identity-auth-manager)** — Configure 3LO auth providers, user consent flows, and RetrieveCredentials permissions.
- **[Google Cloud Secret Manager](https://g.dev/cloud/adventofagents-season3-day6-docs-secret-manager)** — Store, version, and rotate OAuth refresh tokens programmatically for custom REST tools.
