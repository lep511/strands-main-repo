"""Serve the Data Vault agent over A2A, behind an identity check.

The agent card (GET /.well-known/agent-card.json) is public so callers can discover
the agent; every JSON-RPC call (POST) must carry `Authorization: Bearer <token>`
minted by a registered agent that the registry allows to call the Data Vault.

Usage:
    uv run src/module-3/data_vault_server.py          # http://127.0.0.1:9001
"""

import os

import uvicorn
from fastapi import Request
from fastapi.responses import JSONResponse
from strands.multiagent.a2a import A2AServer

from data_vault import authenticate, build_data_vault_agent

HOST = os.getenv("DATA_VAULT_HOST", "127.0.0.1")
PORT = int(os.getenv("DATA_VAULT_PORT", "9001"))

server = A2AServer(agent_factory=build_data_vault_agent, host=HOST, port=PORT)
app = server.to_fastapi_app()


@app.middleware("http")
async def require_agent_identity(request: Request, call_next):
    if request.method == "POST":
        token = request.headers.get("authorization", "").removeprefix("Bearer ").strip()
        try:
            authenticate(token)
        except PermissionError as exc:
            return JSONResponse({"error": f"unauthorized: {exc}"}, status_code=401)
    return await call_next(request)


if __name__ == "__main__":
    uvicorn.run(app, host=HOST, port=PORT)
