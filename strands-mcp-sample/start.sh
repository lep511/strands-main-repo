#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

cleanup() {
  echo "Shutting down..."
  kill "$AGENT_PID" "$MCP_PID" 2>/dev/null || true
  wait "$AGENT_PID" "$MCP_PID" 2>/dev/null || true
}
trap cleanup EXIT

echo "==> Starting Strands Agent (Python) on port 8100..."
cd "$SCRIPT_DIR"
uv run python -m strands_mcp_sample.service &
AGENT_PID=$!

echo "==> Waiting for agent to be ready..."
for i in $(seq 1 30); do
  if curl -sf http://localhost:8100/health >/dev/null 2>&1; then
    echo "    Agent ready."
    break
  fi
  sleep 1
done

echo "==> Starting MCP App server (Node.js) on port 3001..."
cd "$SCRIPT_DIR/mcp-server"
npm run start &
MCP_PID=$!

echo ""
echo "==> Both services running:"
echo "    Strands Agent:  http://localhost:8100"
echo "    MCP App Server: http://localhost:3001/mcp"
echo ""
echo "    Press Ctrl+C to stop."

wait
