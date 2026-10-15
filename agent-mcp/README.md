# Agent MCP — Strands Agent + FastMCP 4 (MCP spec 2026-07-28)

A customer-service MCP server built on FastMCP 4 for the sessionless
[MCP 2026-07-28](https://modelcontextprotocol.io/specification/2026-07-28)
protocol, plus a Strands agent that consumes it as an MCP client.

## Architecture

One virtual environment, two processes. `strands-agents >= 1.61` runs on the
`mcp` 2.x SDK, so the old split (`mcp<2` for Strands, `mcp>=2` for FastMCP 4)
is gone.

```
┌──────────────────────────┐  Streamable HTTP, stateless  ┌──────────────────────────┐
│  Strands agent (CLI)     │ ───────────────────────────▶ │  MCP server (FastMCP 4)  │
│  agent_mcp.agent_service │   POST /mcp (JSON-RPC 2.0)   │  agent_mcp.mcp_server    │
│  MCPClient(url=…)        │ ◀─────────────────────────── │  port 8000               │
│  Bedrock model           │   results / input_required   │  mcp 2.x · protocol      │
└──────────────────────────┘                              │  2026-07-28 (+ legacy)   │
                                                          └──────────────────────────┘
```

Any MCP client works against the server: Claude Code, MCP Inspector, the
FastMCP `Client`, or a handshake-era (`initialize`) client, since FastMCP 4
negotiates the best mutual protocol per connection.

## Setup

```bash
uv sync                # runtime deps
uv sync --group dev    # + pytest
cp .env.example .env   # AWS credentials for Bedrock, server URL
```

## Running

```bash
./start.sh
```

That starts the MCP server in the background and the interactive agent in the
foreground. Or run them separately:

```bash
# Terminal 1 — MCP server → http://0.0.0.0:8000/mcp
uv run python -m agent_mcp.mcp_server
# or: uv run uvicorn agent_mcp.mcp_server:app --port 8000 --workers 4

# Terminal 2 — Strands agent (MCP client)
uv run python -m agent_mcp.agent_service
```

### MCP server on its own

The server has no dependency on the agent, AWS, or Bedrock. Start it alone and
point any MCP client at `http://localhost:8000/mcp` (see "Connect from Claude
Code" and "Test with MCP Inspector" below). Only the agent needs AWS credentials.

### Model

The agent does not pin a model, so it uses the Strands default on Amazon
Bedrock: Claude Sonnet 4.6 via the `global.anthropic.claude-sonnet-4-6`
inference profile, in `AWS_DEFAULT_REGION`. To use another model, pass a
`BedrockModel(model_id=...)` to `Agent(...)` in `agent_service.py`.

## Tools

| Tool | Description | Annotations |
|------|-------------|-------------|
| `list_customers` | All customer IDs and names | readOnly, idempotent |
| `lookup_customer` | Profile for one customer ID | readOnly, idempotent |
| `get_order_history` | Orders for one customer ID | readOnly, idempotent |
| `process_refund` | Refund an order. Asks the user to confirm first | destructive, not idempotent |

Also exposed: a `customer://{customer_id}` resource template with argument
completion for `customer_id`.

## What changed for spec 2026-07-28

| Spec change | Where it shows up here |
|-------------|------------------------|
| No sessions, no `initialize` handshake (SEP-2567, SEP-2575). Every request carries protocol version and capabilities in `_meta`; `server/discover` is the optional probe | `http_app(stateless_http=True)`; Strands `MCPClient(url=…)` probes `server/discover` and negotiates `2026-07-28` |
| Multi round-trip requests replace server-initiated elicitation (SEP-2322). Tools return `resultType: "input_required"`, the client retries with `inputResponses` | `process_refund` is a guard tool: round 1 returns an `InputRequiredResult`, round 2 reads `ctx.input_responses`. The agent's `elicitation_callback` asks the person at the terminal |
| Sealed `requestState` carried between rounds | `REQUEST_STATE_KEY` (optional) so every replica can unseal it |
| Routing headers `Mcp-Method`, `Mcp-Name`, and `x-mcp-header` opt-in for arguments (SEP-2243) | `customer_id` is sent as `Mcp-Param-Customer-Id` for L7 gateways |
| `ttlMs` / `cacheScope` on list and read results (SEP-2549) | `cache_ttl=60`, `cache_scope="public"` |
| Deterministic `tools/list` order for client-side caching | Tools registered in a fixed order; customers sorted |
| Roots, Sampling, Logging deprecated; `ctx.sample()` / `ctx.list_roots()` removed in FastMCP 4 | Not used. Logging goes to stderr |
| mcp 2.x SDK: snake_case fields | `ToolAnnotations(read_only_hint=…)`, `result.is_error`, `tool.input_schema` |

Legacy clients still get the same tools; on a handshake-era connection
`process_refund` falls back to `ctx.elicit()`.

## Tests

```bash
uv run pytest
```

The tests drive the server through the FastMCP in-memory client and check the
negotiated protocol version, cache hints, the routing-header opt-in, and both
outcomes of the refund confirmation round trip.

## Connect from Claude Code

```bash
claude mcp add --transport http customer-service http://localhost:8000/mcp
```

## Test with MCP Inspector

```bash
npx @modelcontextprotocol/inspector --cli http://localhost:8000/mcp \
  --transport http --method tools/list
```

## Environment Variables

| Variable | Default | Used by |
|----------|---------|---------|
| `AWS_DEFAULT_REGION` | `us-east-1` | agent (Bedrock) |
| `MCP_SERVER_URL` | `http://localhost:8000/mcp` | agent |
| `MCP_HOST` / `MCP_PORT` | `0.0.0.0` / `8000` | server |
| `REQUEST_STATE_KEY` | unset (ephemeral per-process key) | server, multi-replica only |

## References

- `context-2026-07-28-version.md` — spec overview clipped from modelcontextprotocol.io
- `fastmcp-4.md` — "What's new in FastMCP 4"
- [Spec changelog 2025-11-25 → 2026-07-28](https://modelcontextprotocol.io/specification/2026-07-28/changelog)
