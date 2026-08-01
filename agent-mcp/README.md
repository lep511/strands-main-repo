# Agent MCP — Strands Agent + FastMCP 4 (spec 2026-07-28)

MCP server that exposes a Strands AI agent via the MCP protocol (spec 2026-07-28).

## Architecture

Two-process design due to dependency conflict (`strands-agents` requires `mcp<2.0`, `fastmcp 4` requires `mcp>=2.0`):

```
┌─────────────────────┐       HTTP        ┌─────────────────────┐
│   MCP Server        │ ───────────────── │   Agent Service     │
│   (FastMCP 4)       │   POST /ask       │   (Strands + FAPI)  │
│   port 8000         │   GET  /health    │   port 8100         │
│   mcp>=2.0          │                   │   mcp<2.0           │
└─────────────────────┘                   └─────────────────────┘
         ▲
         │ MCP protocol (spec 2026-07-28)
         │ stateless HTTP
         ▼
    MCP Client (Claude, Inspector, etc.)
```

## Setup

Each process needs its own virtual environment:

```bash
# 1. Agent Service (Strands)
uv venv .venv-agent
source .venv-agent/bin/activate
uv pip install -e ".[agent-service]"

# 2. MCP Server (FastMCP 4)
uv venv .venv-mcp
source .venv-mcp/bin/activate
uv pip install -e ".[mcp-server]"
```

## Running

```bash
# Terminal 1 — Start the agent service
source .venv-agent/bin/activate
python -m agent_mcp.agent_service
# → Listening on http://0.0.0.0:8100

# Terminal 2 — Start the MCP server
source .venv-mcp/bin/activate
python -m agent_mcp.mcp_server
# → MCP endpoint at http://0.0.0.0:8000/mcp
```

Or use the helper script:

```bash
./start.sh
```

## Tools

| Tool | Description | Annotations |
|------|-------------|-------------|
| `ask_agent` | Send a question to the Strands agent | readOnly, idempotent, openWorld |
| `summarize_text` | Summarize long text via the agent | readOnly, idempotent |
| `get_status` | Health check for server + agent | readOnly, idempotent |

## Spec 2026-07-28 Features

- **Stateless protocol**: no session pinning, `stateless_http=True`
- **Gateway routing headers**: `Mcp-Method`, `Mcp-Name` for L7 routing
- **Explicit handles**: `ask_agent` returns a UUID handle for state threading
- **Response caching**: `cache_ttl=60`, `cache_scope="public"`
- **W3C Trace Context**: compatible with OpenTelemetry

## Connect from Claude Code

```bash
claude mcp add --transport http strands-agent http://localhost:8000/mcp
```

## Test with MCP Inspector

```bash
npx @modelcontextprotocol/inspector --cli http://localhost:8000/mcp \
  --transport http --method tools/list
```

## Environment Variables

| Variable | Default | Used by |
|----------|---------|---------|
| `AWS_DEFAULT_REGION` | `us-east-1` | agent-service |
| `AGENT_SERVICE_URL` | `http://localhost:8100` | mcp-server |
