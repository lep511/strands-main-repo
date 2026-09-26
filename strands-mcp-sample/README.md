# Strands MCP App Sample

An [MCP App](https://github.com/modelcontextprotocol/ext-apps) backed by a [Strands](https://github.com/strands-agents/sdk-python) AI agent. The MCP App renders an interactive UI inside MCP-enabled hosts (like Claude Desktop), while the Strands agent handles tool use and reasoning on the backend.

## Architecture

```
Host (Claude Desktop) ←─MCP─→ Node.js MCP Server (ext-apps) ←─HTTP─→ Python Strands Agent
                                    ↕
                              HTML UI (MCP App)
```

| Component | Port | Description |
|-----------|------|-------------|
| **Strands Agent** | 8100 | FastAPI service running a Strands agent with `get_weather` and `calculate` tools |
| **MCP App Server** | 3001 | Node.js server exposing an `ask-agent` tool with an interactive HTML UI resource |

## Prerequisites

- Python 3.13+
- [uv](https://docs.astral.sh/uv/)
- Node.js 20+

## Setup

```bash
# Python dependencies
uv sync

# Node.js dependencies
cd mcp-server
npm install
npm run build
cd ..
```

## Run

Start both services:

```bash
./start.sh
```

Or run them separately:

```bash
# Terminal 1 — Strands agent
uv run python -m strands_mcp_sample.service

# Terminal 2 — MCP App server
cd mcp-server && npm run start
```

## Test with basic-host

```bash
cd /tmp
git clone --depth 1 https://github.com/modelcontextprotocol/ext-apps.git
cd ext-apps/examples/basic-host
npm install
SERVERS='["http://localhost:3001/mcp"]' npm run start
```

Then open http://localhost:8080 and call the **ask-agent** tool.

## Claude Desktop configuration

Add the MCP server to your Claude Desktop config (`claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "strands-agent": {
      "url": "http://localhost:3001/mcp"
    }
  }
}
```
