#!/usr/bin/env bash
# Start the MCP server in the background and the interactive Strands agent in
# the foreground. One virtual environment serves both (see README).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

if [ ! -x .venv/bin/python ]; then
  echo "No .venv found. Run:  uv sync" >&2
  exit 1
fi

MCP_PORT="${MCP_PORT:-8000}"
export MCP_SERVER_URL="${MCP_SERVER_URL:-http://localhost:${MCP_PORT}/mcp}"

echo "=== Starting MCP Server (spec 2026-07-28) on port ${MCP_PORT} ==="
.venv/bin/python -m agent_mcp.mcp_server &
MCP_PID=$!
trap 'kill "$MCP_PID" 2>/dev/null || true' EXIT INT TERM

# Wait for the endpoint to answer server/discover before starting the agent.
for _ in $(seq 1 30); do
  if curl -fsS -o /dev/null -X POST "$MCP_SERVER_URL" \
       -H 'Content-Type: application/json' \
       -H 'Accept: application/json, text/event-stream' \
       -H 'Mcp-Method: server/discover' \
       -d '{"jsonrpc":"2.0","id":0,"method":"server/discover","params":{}}' 2>/dev/null; then
    break
  fi
  sleep 0.5
done

echo "=== Starting Strands agent (MCP client → ${MCP_SERVER_URL}) ==="
.venv/bin/python -m agent_mcp.agent_service
