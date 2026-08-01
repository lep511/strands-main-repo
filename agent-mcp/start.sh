#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

echo "=== Starting Agent Service (port 8100) ==="
source .venv-agent/bin/activate
python -m agent_mcp.agent_service &
AGENT_PID=$!
deactivate

sleep 2

echo "=== Starting MCP Server (port 8000) ==="
source .venv-mcp/bin/activate
python -m agent_mcp.mcp_server &
MCP_PID=$!
deactivate

echo ""
echo "Agent Service PID: $AGENT_PID (http://localhost:8100)"
echo "MCP Server PID:    $MCP_PID (http://localhost:8000/mcp)"
echo ""
echo "Press Ctrl+C to stop both."

trap "kill $AGENT_PID $MCP_PID 2>/dev/null; exit" INT TERM
wait
