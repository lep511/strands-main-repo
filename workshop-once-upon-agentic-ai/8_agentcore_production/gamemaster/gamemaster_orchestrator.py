import os
import uuid
import boto3
import httpx
from dotenv import load_dotenv
from pydantic import BaseModel, Field
from strands import Agent
from strands.vended_tools import make_a2a_client
from strands.tools.mcp import MCPClient
from mcp_proxy_for_aws.client import aws_iam_streamablehttp_client
from a2a.client import ClientConfig
from mcp_proxy_for_aws.sigv4_helper import SigV4HTTPXAuth
from bedrock_agentcore.runtime import BedrockAgentCoreApp
from bedrock_agentcore.memory.integrations.strands.config import AgentCoreMemoryConfig
from bedrock_agentcore.memory.integrations.strands.session_manager import AgentCoreMemorySessionManager

app = BedrockAgentCoreApp()

# The URLs of your runtimes are read from the .env file of the chapter folder (see .env.example)
load_dotenv()

DICE_SERVER_URL = os.environ["DICE_SERVER_URL"]

mcp_client = MCPClient(
    lambda: aws_iam_streamablehttp_client(
        endpoint=DICE_SERVER_URL,
        aws_service="bedrock-agentcore",
    )
)

CHARACTER_AGENT_URL = os.environ["CHARACTER_AGENT_URL"]

_session = boto3.Session()
agentcore_config = ClientConfig(
    httpx_client=httpx.AsyncClient(
        auth=SigV4HTTPXAuth(
            _session.get_credentials(),
            "bedrock-agentcore",
            _session.region_name,
        ),
        headers={"x-amz-bedrock-agentcore-session-id": str(uuid.uuid4())},
    )
)

RULES_AGENT_URL = os.environ["RULES_AGENT_URL"]

class DiceOutput(BaseModel):
    dice_type: str = Field(description="The dice type. Ex: d4, d6, d20, etc")
    result: int = Field(description="The dice result value alone")
    reason: str = Field(description="The reason the dice was rolled. Ex: attack roll. And the modificators if there was any")

class StoryOutput(BaseModel):
    """A single Game Master turn: the narration, what the player could do next, and any dice rolled."""
    response: str = Field(description="Your narative response as Game Master")
    actions_suggestions: list[str] = Field(description="['Action 1', 'Action 2', 'Action 3']")
    details: str = Field(description="Brief summary of tools/agents used")
    dice_rolls: list[DiceOutput] = Field(default=[], description="List of dice rolls with dice_type, result, and reason")



a2a_client = make_a2a_client(allowed_endpoints=[
    (RULES_AGENT_URL, agentcore_config),
    (CHARACTER_AGENT_URL, agentcore_config),
])

# One Game Master per session, created on its first invocation
game_masters = {}

def get_game_master(session_id: str) -> Agent:
    if session_id not in game_masters:
        game_masters[session_id] = Agent(
            system_prompt="""You are a Game Master for a fantasy role-playing game. Discover the agents you can reach and ask them instead of guessing: rules questions, character creation and lookups are their job. Every dice roll goes through roll_dice. Never make up what a tool can tell you, and narrate with flair.""",
            tools=[mcp_client, a2a_client],
            structured_output_model=StoryOutput,
            session_manager=AgentCoreMemorySessionManager(
                AgentCoreMemoryConfig(
                    memory_id=os.environ["MEMORY_CONVERSATIONS_ID"],
                    session_id=session_id,
                    actor_id="player",
                )
            ),
        )
    return game_masters[session_id]

@app.entrypoint
async def invoke(payload):
    session_id = payload.get("session_id", "default-campaign")
    if payload.get("messages"):
        return get_game_master(session_id).messages
    prompt = payload.get("prompt", "Hello")
    response = await get_game_master(session_id).invoke_async(prompt)
    return response.structured_output.model_dump()

if __name__ == "__main__":
    app.run()
