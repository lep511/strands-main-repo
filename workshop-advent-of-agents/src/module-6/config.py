"""Names shared by every Day 6 script. Override with environment variables."""

import os

from dotenv import load_dotenv

load_dotenv()

REGION = os.getenv("AWS_REGION", "us-east-1")
# Sonnet on Bedrock. Adaptive-thinking Sonnet models reject temperature/top_p, so none are set.
MODEL_ID = os.getenv("MODEL_ID", "us.anthropic.claude-sonnet-5-5")

# AgentCore Identity resources (~ the auth provider and the agent identity of the original)
PROVIDER_NAME = os.getenv("PROVIDER_NAME", "github-oauth-provider")
WORKLOAD_NAME = os.getenv("WORKLOAD_NAME", "aoa_day06_devops")
SCOPES = ["repo", "read:user"]

# The app's session-binding endpoint (~ continue_uri / validateUserId of the original)
APP_PORT = int(os.getenv("APP_PORT", "8501"))
RETURN_URL = os.getenv("OAUTH_RETURN_URL", f"http://localhost:{APP_PORT}/oauth2/callback")

GITHUB_MCP_URL = "https://api.githubcopilot.com/mcp/"

# Placeholders until GitHub issues the real client (it needs the callback URL first).
PLACEHOLDER_CLIENT_ID = "placeholder-client-id"
PLACEHOLDER_CLIENT_SECRET = "placeholder-client-secret"
