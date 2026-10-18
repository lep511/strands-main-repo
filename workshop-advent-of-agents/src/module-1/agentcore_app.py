"""SCALE (preview of Day 5): the same agent served the way AgentCore Runtime expects.

BedrockAgentCoreApp exposes POST /invocations and GET /ping on port 8080, which is
the HTTP contract of Amazon Bedrock AgentCore Runtime.

Usage:
    uv run --group deploy src/module-1/agentcore_app.py
    curl -s -X POST http://localhost:8080/invocations \
        -H "Content-Type: application/json" \
        -d '{"prompt": "What time is it in Madrid?"}'
"""

from bedrock_agentcore.runtime import BedrockAgentCoreApp

from adlc_agent import build_agent
from spec_guard import SpecGuard

app = BedrockAgentCoreApp()


@app.entrypoint
def invoke(payload: dict) -> dict:
    guard = SpecGuard(verbose=False)
    # A fresh agent per request keeps conversations from leaking between callers.
    agent = build_agent(guard=guard, callback_handler=None)
    result = agent(payload.get("prompt", "What's the weather in San Francisco?"))
    return {"result": str(result), "tool_calls": guard.audit_log}


if __name__ == "__main__":
    app.run()
