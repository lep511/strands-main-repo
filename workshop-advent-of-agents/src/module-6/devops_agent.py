"""The DevOps Assistant: a Strands agent on Sonnet that reads GitHub AS the signed-in user.

The GitHub MCP server receives the user's own OAuth token, so GitHub applies that user's
permissions. Read-only is enforced twice: the server's read-only mode (X-MCP-Readonly)
and a Strands hook that cancels any tool whose name looks like a write.
"""

import re

from strands import Agent
from strands.hooks import BeforeToolCallEvent, HookProvider, HookRegistry
from strands.models import BedrockModel
from strands.tools.mcp import MCPClient

from config import GITHUB_MCP_URL, MODEL_ID, REGION

INSTRUCTION = """You are the DevOps Assistant. You help developers list and triage their GitHub issues and pull requests.
Your capabilities: you have a GitHub MCP toolset that you can use to perform actions that the user requests.

Rules:
- NEVER write, update, or delete. You are only allowed read access.
- Act on behalf of the signed-in user.
- If a tool returns an authentication or authorization error, guide the user to sign in.
- NEVER fabricate information. Only report real issues returned by tools.
"""

# GitHub MCP read tools look like get_me, list_issues, search_code, issue_read, pull_request_read.
WRITE_TOOL = re.compile(
    r"^request_|(^|_)(create|update|delete|merge|push|add|remove|fork|assign|dismiss|submit|write|edit|close|reopen|lock|star|unstar)(_|$)"
)


class ReadOnlyGuard(HookProvider):
    """Defense in depth: even if the server exposed a write tool, the agent cannot call it."""

    def register_hooks(self, registry: HookRegistry) -> None:
        registry.add_callback(BeforeToolCallEvent, self.check)

    def check(self, event: BeforeToolCallEvent) -> None:
        name = event.tool_use["name"]
        if WRITE_TOOL.search(name):
            event.cancel_tool = f"Tool '{name}' is not read-only; the DevOps Assistant may only read."


def github_mcp(user_token: str) -> MCPClient:
    """GitHub's remote MCP server, authenticated as the USER (not as the agent)."""
    return MCPClient(
        url=GITHUB_MCP_URL,
        headers={
            "Authorization": f"Bearer {user_token}",
            "X-MCP-Toolsets": "repos,issues,pull_requests,users,context",
            "X-MCP-Readonly": "true",
        },
    )


def build_agent(user_token: str) -> Agent:
    return Agent(
        name="devops-assistant",
        model=BedrockModel(model_id=MODEL_ID, region_name=REGION),
        system_prompt=INSTRUCTION,
        tools=[github_mcp(user_token)],
        hooks=[ReadOnlyGuard()],
        callback_handler=None,
    )
