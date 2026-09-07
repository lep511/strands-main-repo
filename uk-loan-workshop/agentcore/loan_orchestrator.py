#!/usr/bin/env python3
"""
Loan Orchestrator Agent
Coordinates 5 Lambda specialist agents via AgentCore Gateway.

Deployed on Amazon Bedrock AgentCore Runtime.
Uses BedrockAgentCoreApp (@app.entrypoint) as required by the Runtime service contract.

The entrypoint is an async generator, so the Runtime streams the response
(text/event-stream). Clients receive progress events in real time:
    {"type": "tool_use", "tool": "<gateway tool name>"}   specialist agent invoked
    {"type": "delta",    "text": "<chunk>"}               response text as generated
    {"type": "final",    "result": "<full response>"}     end of turn
"""

import os
from bedrock_agentcore import BedrockAgentCoreApp
from strands import Agent
from strands.models import BedrockModel
from strands.tools.mcp.mcp_client import MCPClient
from mcp.client.streamable_http import streamablehttp_client

app = BedrockAgentCoreApp()

SYSTEM_PROMPT = """You are the Loan Orchestrator for a UK short-term personal loan system.

You coordinate 5 specialist agents to process loan applications:
1. account-data-loader - Creates and verifies customer accounts
2. eligibility-filter - Performs KYC and eligibility checks
3. loan-product-matcher - Creates FCA-compliant loan products
4. risk-assessment - Handles PIN security
5. approval-decision - Makes final approval and disburses funds

Process applications sequentially through all 5 agents.
Guide customers through the loan application process."""

# Modified system prompt for Korean-speaking customers.
# Selected when the frontend (app-kor.py) sends {"language": "ko"} in the payload.
SYSTEM_PROMPT_KO = SYSTEM_PROMPT + """

The customer speaks Korean. ALWAYS respond in natural, polite Korean (존댓말).
Keep identifiers and data values exactly as provided - names, National Insurance
Numbers, sort codes, account numbers, loan IDs and amounts such as £2,000.
Translate everything else: questions, explanations, confirmations and status updates."""

# Initialize agent once at module load (not per-request)
GATEWAY_URL = os.environ.get('GATEWAY_URL')
if not GATEWAY_URL:
    raise ValueError("GATEWAY_URL environment variable required")

model = BedrockModel(
    model_id=os.environ.get('BEDROCK_MODEL_ID', 'us.anthropic.claude-sonnet-4-6'),
    region_name=os.environ.get('AWS_DEFAULT_REGION', 'us-east-1'),
)


def _create_agent(system_prompt):
    # Each agent gets its own MCP connection to the Gateway
    mcp_client = MCPClient(lambda: streamablehttp_client(GATEWAY_URL))
    return Agent(model=model, system_prompt=system_prompt, tools=[mcp_client])


# The English agent is created at module load (default path); the Korean
# agent is created lazily on the first Korean request.
AGENTS = {'en': _create_agent(SYSTEM_PROMPT)}


def _get_agent(language):
    if language == 'ko' and 'ko' not in AGENTS:
        AGENTS['ko'] = _create_agent(SYSTEM_PROMPT_KO)
    return AGENTS.get(language, AGENTS['en'])


@app.entrypoint
async def invoke(payload):
    """AgentCore Runtime entrypoint — invoked per request, streams events."""
    query = payload.get('query', payload.get('prompt', payload.get('message', str(payload))))
    language = payload.get('language', 'en')

    # Inject conversation history if provided (the client includes the current
    # message as the last entry, so only earlier turns count as history)
    history = payload.get('history', [])
    if len(history) > 1:
        history_lines = '\n'.join(
            f"{h.get('role','user').upper()}: {h.get('content','')}"
            for h in history[:-1]
        )
        query = f"Previous conversation:\n{history_lines}\n\nCurrent message: {query}"

    agent = _get_agent(language)

    seen_tool_ids = set()
    chunks = []
    final_result = None
    async for event in agent.stream_async(query):
        tool_use = event.get('current_tool_use') or {}
        if tool_use.get('name') and tool_use.get('toolUseId') not in seen_tool_ids:
            seen_tool_ids.add(tool_use.get('toolUseId'))
            yield {"type": "tool_use", "tool": tool_use['name']}
        if 'data' in event:
            text = event['data'] if isinstance(event['data'], str) else str(event['data'])
            chunks.append(text)
            yield {"type": "delta", "text": text}
        if 'result' in event:
            final_result = event['result']

    result_text = str(final_result) if final_result is not None else ''.join(chunks)
    yield {"type": "final", "result": result_text}


if __name__ == '__main__':
    app.run()
