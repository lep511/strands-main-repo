"""Call the AgentCore Gateway as the support agent's identity (SigV4, AWS_IAM inbound auth)."""

import json

import boto3
import httpx
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest
from strands.tools.mcp import MCPClient

from config import AGENT_ROLE, REGION, require_state


def agent_session() -> boto3.Session:
    """Assume the agent's own role. Every gateway call is then signed AS THE AGENT."""
    account = boto3.client("sts", region_name=REGION).get_caller_identity()["Account"]
    creds = boto3.client("sts", region_name=REGION).assume_role(
        RoleArn=f"arn:aws:iam::{account}:role/{AGENT_ROLE}", RoleSessionName="customer-support-agent"
    )["Credentials"]
    return boto3.Session(
        aws_access_key_id=creds["AccessKeyId"],
        aws_secret_access_key=creds["SecretAccessKey"],
        aws_session_token=creds["SessionToken"],
        region_name=REGION,
    )


class SigV4HttpxAuth(httpx.Auth):
    """Sign each MCP request for the bedrock-agentcore service."""

    requires_request_body = True

    def __init__(self, session: boto3.Session, region: str = REGION):
        self.credentials = session.get_credentials()
        self.region = region

    def auth_flow(self, request: httpx.Request):
        headers = {k: v for k, v in request.headers.items() if k.lower() in {"content-type", "accept", "mcp-protocol-version"}}
        aws_request = AWSRequest(method=request.method, url=str(request.url), data=request.content, headers=headers)
        SigV4Auth(self.credentials.get_frozen_credentials(), "bedrock-agentcore", self.region).add_auth(aws_request)
        for key, value in aws_request.headers.items():
            request.headers[key] = value
        yield request


def mcp_client(session: boto3.Session) -> MCPClient:
    return MCPClient(url=require_state("gateway_url"), auth_provider=SigV4HttpxAuth(session))


def raw_tool_call(session: boto3.Session, tool: str, arguments: dict) -> tuple[int, dict]:
    """A bare JSON-RPC tools/call, like the original's httpx.post(...). Returns (status, body)."""
    payload = {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": tool, "arguments": arguments}}
    response = httpx.post(
        require_state("gateway_url"),
        content=json.dumps(payload),
        headers={"Content-Type": "application/json", "Accept": "application/json, text/event-stream"},
        auth=SigV4HttpxAuth(session),
        timeout=30,
    )
    try:
        body = response.json()
    except ValueError:
        body = {"raw": response.text[:500]}
    return response.status_code, body
